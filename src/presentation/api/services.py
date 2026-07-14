"""
Presentation/API: services

Toda la lógica real de la API vive acá, sin importar FastAPI ni
Pydantic -- los routers (`presentation/api/routers/*.py`) son
deliberadamente delgados: reciben el request, llaman a una función de
acá, envuelven el resultado en un schema. Esto separa "qué hace cada
endpoint" de "cómo se sirve por HTTP", y como consecuencia, todo este
archivo se puede testear sin tener fastapi/uvicorn instalados -- que es
exactamente la situación en la que se escribió (ver changelog de
docs/ARCHITECTURE_V3_FASTAPI_MIGRATION.md: el entorno donde se construyó
esta capa no tenía esas dependencias disponibles).

Nada acá decide reglas de negocio nuevas -- todo delega en
OpportunityEngine / DetectOpportunitiesUseCase / los repositorios ya
existentes, igual que hacía `app.py` de Streamlit.
"""

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import List, Optional, Tuple, Dict, Any
import os
import sqlite3
from shared.db import connect_db
import secrets
import time
from datetime import datetime, timezone, timedelta

from application.use_cases.detect_opportunities_use_case import (
    DetectOpportunitiesUseCase, DetectOpportunitiesRequest
)
from domain.services.opportunity_engine import OpportunityEngine
from domain.value_objects.opportunity import Opportunity
from domain.value_objects.fee_profile import FeeProfile
from domain.value_objects.user import User
from infrastructure.repositories.sqlite_market_repository import SQLiteMarketRepository
from infrastructure.repositories.sqlite_type_repository import SQLiteTypeRepository, JITA_REGION_ID
from domain.value_objects.trade_hub import get_hub, TRADE_HUBS

JITA_STATION_ID = TRADE_HUBS["jita"].station_id
from infrastructure.repositories.sqlite_user_repository import SQLiteUserRepository
from infrastructure.jobs.seed_job import SmartAutoSeedJob, SeedResult
from infrastructure.jobs.sync_status_repository import SyncStatusRepository
from infrastructure.auth.eve_sso_client import EveSSOClient, EveSSOError, generate_pkce_pair, build_authorize_url
from infrastructure.security.token_encryption import TokenEncryptor
from infrastructure.security.session_tokens import (
    issue_session_token, verify_session_token, SessionTokenError
)
from shared.paths import DEFAULT_DB_PATH
from shared.eta import estimate_seconds_remaining, format_eta
from infrastructure.observability.logging_setup import get_logger

logger = get_logger("services")

DEFAULT_FEE_PROFILE = FeeProfile(entry_fee_rate=0.03, exit_fee_rate=0.036)


@dataclass(frozen=True)
class OpportunitiesPage:
    """
    Resultado de una consulta de oportunidades, ya ordenado y acotado.

    `opportunities` son pares (Opportunity, confidence) -- confidence
    viene de `AnalysisResult.confidence` (ver domain/value_objects/analysis_result.py),
    no de `Opportunity` en sí. v1.1: antes se perdía en el camino (solo
    se guardaba `.value`), lo que hubiera dejado a Streamlit sin la
    señal de "confianza del análisis" al migrar de llamar al use case
    directo a consumir la API -- se detectó al planear esa migración.
    """
    opportunities: List[Tuple[Opportunity, float]]
    total_evaluated: int
    total_with_data: int
    scope: str  # "discovery" | "tracked"


class ApiServices:
    """
    Punto único de construcción de los repos/engines/use cases que
    consumen los routers. Vive acá (no en cada router) para que haya un
    solo lugar donde cablear dependencias -- mismo espíritu que
    `dependencies.py` de FastAPI, pero sin necesitar FastAPI para
    testearlo.
    """

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        region_id: int = JITA_REGION_ID,
        station_id: int = JITA_STATION_ID,
        fee_profile: FeeProfile = DEFAULT_FEE_PROFILE,
    ):
        self.db_path = db_path
        self.region_id = region_id
        #: v2 (modularización multi-hub): antes NINGÚN caller de este
        #: servicio pasaba `location_id` explícito a los métodos del
        #: repositorio -- todos confiaban en el default de
        #: `SQLiteMarketRepository` (JITA_STATION_ID hardcodeado). Eso
        #: significaba que cambiar `region_id` a otro hub (ej. Amarr)
        #: sin arreglar esto hubiera seguido filtrando por la estación
        #: de JITA -- región de un hub, estación de otro, resultados
        #: vacíos o mezclados. Ahora `station_id` es explícito acá y se
        #: pasa a cada llamada del repositorio, ver `for_hub()`.
        self.station_id = station_id
        self.fee_profile = fee_profile

        self.type_repo = SQLiteTypeRepository(db_path=db_path)
        self.market_repo = SQLiteMarketRepository(db_path=db_path)
        self.user_repo = SQLiteUserRepository(db_path=db_path)
        self.opportunity_engine = OpportunityEngine()
        self.use_case = DetectOpportunitiesUseCase(self.market_repo, self.type_repo, self.opportunity_engine)
        self.status_repo = SyncStatusRepository(db_path=db_path)

        # EVE SSO -- None si no está configurado (faltan las env vars).
        # Deliberadamente NO explota en __init__: la API tiene que poder
        # arrancar igual para desarrollo/tests sin credenciales de EVE
        # todavía, el error recién aparece si alguien intenta loguearse
        # de verdad sin esto configurado (ver get_eve_login_url).
        eve_client_id = os.environ.get("EVE_SSO_CLIENT_ID")
        eve_client_secret = os.environ.get("EVE_SSO_CLIENT_SECRET")
        self.eve_sso_client: Optional[EveSSOClient] = (
            EveSSOClient(client_id=eve_client_id, client_secret=eve_client_secret)
            if eve_client_id and eve_client_secret else None
        )

        # Mapeo state->code_verifier del flujo OAuth2/PKCE, en memoria de
        # proceso -- el login abarca DOS requests separados (redirect a
        # EVE, después el callback), necesitamos recordar el verifier
        # entre uno y otro. TTL corto (10 min) porque si el usuario nunca
        # completa el login, no queremos que esto crezca sin límite.
        # ⚠️ Limitación conocida: esto NO sobrevive un restart del
        # proceso, y no funciona si algún día se corre con más de un
        # worker de uvicorn (cada worker tendría su propio dict). Para
        # un solo proceso (el modo en que corre hoy) es correcto y
        # simple; si se pasa a multi-worker, esto necesita mudarse a
        # una tabla de DB o a algo compartido como Redis.
        self._oauth_pending: Dict[str, Tuple[str, float]] = {}
        self._oauth_pending_lock = Lock()
        self.OAUTH_STATE_TTL_SECONDS = 600

        self._token_encryptor: Optional[TokenEncryptor] = None

        # Serializa corridas del Smart Auto-Seed: el arranque de la API
        # lo dispara solo (primera vez) Y hay un endpoint manual
        # (POST /api/sync/seed) -- sin este lock, un usuario que dispara
        # el endpoint justo cuando el auto-seed de arranque ya está
        # corriendo termina con DOS SmartAutoSeedJob.run() concurrentes
        # sobre la misma región (visto en la práctica: pasó en la
        # primera corrida real). No corrompe datos (SQLite en WAL
        # serializa escrituras), pero duplica trabajo contra ESI y hace
        # que sync_status parpadee con progreso de dos corridas
        # entreveradas.
        self._seed_lock = Lock()

    @classmethod
    def for_hub(cls, hub_key: str, db_path: Path = DEFAULT_DB_PATH, **kwargs) -> "ApiServices":
        """
        Construye un `ApiServices` para un hub de trading específico
        (ver `domain.value_objects.trade_hub.TRADE_HUBS`), resolviendo
        `region_id`/`station_id` juntos desde el registro -- nunca por
        separado, para no correr el riesgo de emparejar la región de un
        hub con la estación de otro (el bug de "Jita vs. La Forge
        entera" en otra forma).
        """
        hub = get_hub(hub_key)
        return cls(db_path=db_path, region_id=hub.region_id, station_id=hub.station_id, **kwargs)

    # ------------------------------------------------------------------
    # Oportunidades
    # ------------------------------------------------------------------

    def list_opportunities(
        self,
        scope: str = "discovery",
        min_score: float = 0.0,
        max_results: int = 50,
        sort_by: str = "score",
        sort_desc: bool = True,
        discovery_limit: int = 30000,
        exclude_caution: bool = False,
        user_id: Optional[int] = None,
    ) -> OpportunitiesPage:
        """
        scope="discovery": TODO lo que tenga order book bidireccional
        activo en la región (post Smart Auto-Seed, esto es potencialmente
        miles de ítems -- ya no depende de qué esté trackeado a mano).
        `discovery_limit` acota cuántos de esos ítems se evalúan como
        máximo (default 30000, cubre la región completa de Jita hoy con
        margen -- ver changelog en `SQLiteMarketRepository.get_active_type_ids`).
        scope="tracked": solo la watchlist personal de `user_id` --
        OBLIGATORIO para este scope (ver v2, multi-tenancy: antes había
        un solo usuario implícito, ahora cada watchlist tiene dueño).

        `exclude_caution=True` saca del ranking cualquier ítem cuya
        `recommendation` sea una categoría `caution_*` (liquidez
        fantasma, order book fino, sin evidencia de volumen, riesgo
        alto). No toca el score en sí -- sigue siendo el mismo número
        auditable de siempre (`sum_of_contributions == final_score`),
        esto es un filtro aparte, explícito y opt-in, no una
        penalización mezclada en la matemática del score. Nace de un
        caso real: ítems tipo SKIN con ROI de troll orders (1 sola
        orden, ROI en los millones de %) sacaban score 52-56 -- ya
        marcados `caution_thin_order_book` correctamente, pero igual
        aparecían en el top-50 por score, obligando a leer cada motivo
        para separar oportunidades reales de ruido.
        """
        if scope == "tracked":
            if user_id is None:
                raise ValueError("scope='tracked' requiere un user_id -- no hay watchlist sin dueño.")
            type_ids = self.type_repo.tracked_type_ids(user_id, self.region_id)
        elif scope == "discovery":
            type_ids = self.market_repo.get_active_type_ids(self.region_id, limit=discovery_limit, location_id=self.station_id)
        else:
            raise ValueError(f"scope inválido: {scope!r} (usar 'discovery' o 'tracked')")

        if not type_ids:
            return OpportunitiesPage(opportunities=[], total_evaluated=0, total_with_data=0, scope=scope)

        request = DetectOpportunitiesRequest(
            type_ids=type_ids, region_id=self.region_id, station_id=self.station_id, fee_profile=self.fee_profile
        )
        # min_score=0 y max_results=len(type_ids) a propósito: le pedimos
        # al use case TODO lo evaluado, sin cortar. El filtrado real
        # (min_score, exclude_caution) y el ordenamiento se hacen acá
        # abajo, sobre el conjunto completo -- antes se le pasaba
        # `max_results * 3` como margen para poder reordenar por un
        # campo distinto a score sin perder ítems del borde, pero eso
        # era un parche heurístico, no una garantía: con exclude_caution
        # (o cualquier filtro que recorte bastante el pool) un margen
        # fijo de "3x" podía devolver menos de max_results igual. Pedir
        # todo no cuesta más -- el use case ya calcula todos los
        # resultados de por sí, el corte por max_results era solo un
        # slice al final.
        result = self.use_case.execute(request, min_score=0.0, max_results=len(type_ids))

        pool = [r for r in result.ranked_all if r.value.score >= min_score]
        if exclude_caution:
            pool = [r for r in pool if not r.value.recommendation.is_caution]

        sorted_pool = self._sort_opportunities(pool, sort_by, sort_desc)
        opportunities = [(r.value, r.confidence) for r in sorted_pool[:max_results]]

        return OpportunitiesPage(
            opportunities=opportunities,
            total_evaluated=len(type_ids),
            total_with_data=result.summary.get("con_evidencia_suficiente", 0),
            scope=scope,
        )

    @staticmethod
    def _sort_opportunities(results: list, sort_by: str, sort_desc: bool) -> list:
        key_fn = {
            "score": lambda r: r.value.score,
            "roi": lambda r: r.value.roi_percent,
            "liquidity": lambda r: r.value.liquidity.liquidity_score,
        }.get(sort_by)
        if key_fn is None:
            raise ValueError(f"sort_by inválido: {sort_by!r} (usar 'score', 'roi' o 'liquidity')")
        return sorted(results, key=key_fn, reverse=sort_desc)

    def get_opportunity_detail(self, type_id: int) -> Optional[Tuple[Opportunity, float]]:
        snapshot = self.market_repo.get_current_snapshot(type_id, self.region_id, location_id=self.station_id)
        if snapshot is None:
            return None
        type_info = self.type_repo.get(type_id)
        if type_info is None:
            return None

        from domain.services.opportunity_engine import OpportunityInput
        sell_count, buy_count = self.market_repo.order_counts(type_id, self.region_id, location_id=self.station_id)
        opportunity_input = OpportunityInput(
            instrument_id=type_id,
            instrument_name=type_info.get("name", f"Type-{type_id}"),
            market_id=self.region_id,
            buy_price=snapshot.buy_price,
            sell_price=snapshot.sell_price,
            daily_volume=snapshot.daily_volume,
            total_sell_volume_remain=self.market_repo.total_sell_volume_remain(type_id, self.region_id, location_id=self.station_id),
            total_buy_volume_remain=self.market_repo.total_buy_volume_remain(type_id, self.region_id, location_id=self.station_id),
            sell_order_count=sell_count,
            buy_order_count=buy_count,
            fee_profile=self.fee_profile,
        )
        result = self.opportunity_engine.detect(opportunity_input)
        return result.value, result.confidence

    # ------------------------------------------------------------------
    # Tracked items (watchlist personal) -- todos requieren user_id
    # desde v2 (multi-tenancy). No hay default: una watchlist sin dueño
    # ya no es un concepto válido en el sistema.
    # ------------------------------------------------------------------

    def list_tracked_type_ids(self, user_id: int) -> List[int]:
        return self.type_repo.tracked_type_ids(user_id, self.region_id)

    def list_tracked_items(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Watchlist personal de `user_id`, con nombres resueltos, no solo
        type_ids -- para que la UI pueda mostrar una lista legible (ej.
        el preview del sidebar) sin pedir el análisis completo
        (`OpportunityEngine.detect`) solo para leer un nombre. Usa
        `get_names_bulk` (una query), no una conexión por ítem.
        """
        type_ids = self.type_repo.tracked_type_ids(user_id, self.region_id)
        if not type_ids:
            return []
        names = self.type_repo.get_names_bulk()
        return [{"type_id": tid, "name": names.get(tid, f"Type-{tid}")} for tid in type_ids]

    def track_item(self, user_id: int, type_id: int, reason: Optional[str] = None) -> None:
        self.type_repo.track(user_id, type_id, self.region_id, reason=reason)

    def untrack_item(self, user_id: int, type_id: int) -> None:
        self.type_repo.untrack(user_id, type_id, self.region_id)

    def untrack_many_items(self, user_id: int, type_ids: List[int]) -> int:
        return self.type_repo.untrack_many(user_id, type_ids, self.region_id)

    def untrack_all_items(self, user_id: int) -> int:
        return self.type_repo.untrack_all(user_id, self.region_id)

    def search_items(self, query: str, limit: int = 20) -> List[dict]:
        return self.type_repo.search(query, limit=limit)

    def list_categories(self) -> List[dict]:
        """
        Categorías del catálogo (SDE) con items publicados -- para el
        explorador de Categoría → Grupo. Existía como método del
        repositorio desde hace tiempo, pero nunca se expuso vía HTTP --
        solo Streamlit lo usaba (acceso directo a la DB). NiceGUI
        necesita esto como endpoint real, ver `routers/catalog.py`.
        """
        return self.type_repo.get_distinct_categories()

    def list_groups_by_category(self, category_id: int) -> List[dict]:
        return self.type_repo.get_groups_by_category(category_id)

    def list_types_in_group(self, group_id: int, limit: int = 40) -> List[dict]:
        return self.type_repo.get_types_in_group(group_id, limit=limit)

    # ------------------------------------------------------------------
    # Sync / Smart Auto-Seed
    # ------------------------------------------------------------------

    def get_sync_status(self) -> Optional[dict]:
        """
        Estado del último/actual Smart Auto-Seed, enriquecido con
        `eta_seconds`/`eta_human` -- calculado acá (no en cada UI) para
        que Streamlit, NiceGUI y cualquier cliente futuro muestren el
        mismo número sin duplicar el cálculo. Ver `shared/eta.py` para
        el porqué: un usuario real esperó sin feedback de tiempo
        durante una corrida larga y llegó a pensar que estaba roto.
        """
        status = self.status_repo.get_status(self.region_id)
        if status is None:
            return None
        eta_seconds = estimate_seconds_remaining(
            total=status.get("total"), done=status.get("done"),
            started_at=status.get("started_at"),
        )
        status["eta_seconds"] = eta_seconds
        status["eta_human"] = format_eta(eta_seconds)
        return status

    def needs_initial_seed(self) -> bool:
        return self.status_repo.needs_initial_seed()

    def run_seed_job(self) -> SeedResult:
        """
        Corre el Smart Auto-Seed de forma SÍNCRONA (bloqueante). El
        router que lo dispare debe hacerlo desde un BackgroundTask de
        FastAPI, no en el request path -- ver `routers/sync.py`.

        Serializado con `_seed_lock`: si ya hay una corrida en curso
        (disparada por el auto-seed de arranque o por otro request),
        levanta `RuntimeError` en vez de arrancar una segunda en
        paralelo. El caller (router) debería chequear
        `is_seed_running()` ANTES de encolar el background task para
        poder responder algo útil al cliente en vez de que el error
        quede silencioso dentro del BackgroundTask.
        """
        if not self._seed_lock.acquire(blocking=False):
            raise RuntimeError(
                "Ya hay un Smart Auto-Seed en curso para esta región. "
                "Esperá a que termine (GET /api/sync/status) antes de disparar otro."
            )
        try:
            job = SmartAutoSeedJob(db_path=self.db_path, region_id=self.region_id, status_repo=self.status_repo)
            return job.run()
        finally:
            self._seed_lock.release()

    def is_seed_running(self) -> bool:
        """
        True si hay una corrida de Smart Auto-Seed en curso ahora mismo.
        Usado por el router para decidir si vale la pena encolar otra,
        o devolver "ya está corriendo" sin duplicar trabajo.
        """
        acquired = self._seed_lock.acquire(blocking=False)
        if acquired:
            self._seed_lock.release()
            return False
        return True

    # ------------------------------------------------------------------
    # Autenticación (EVE SSO)
    # ------------------------------------------------------------------

    def get_eve_login_url(self, redirect_uri: str, frontend_redirect: str) -> str:
        """
        URL a la que el frontend debe redirigir al usuario para iniciar
        el login. Genera y guarda un par PKCE + state, para verificar
        en `handle_eve_callback` que la vuelta corresponde a este mismo
        intento de login (protege contra CSRF y contra que alguien use
        un `code` interceptado de otra sesión).

        `redirect_uri`: el callback de ESTA api (`/api/auth/callback`)
        -- el que EVE SSO usa para devolver el control después de que
        el usuario aprueba el login. Tiene que coincidir EXACTO con lo
        que se configuró en developers.eveonline.com.

        `frontend_redirect`: a dónde mandar al browser una vez que el
        login terminó del todo (la URL de Streamlit o NiceGUI que
        inició el flujo) -- ninguno de los dos es "el" frontend fijo,
        cualquier UI que implemente el mismo patrón puede loguearse.
        """
        if self.eve_sso_client is None:
            raise ValueError(
                "EVE SSO no está configurado -- faltan EVE_SSO_CLIENT_ID / "
                "EVE_SSO_CLIENT_SECRET en el entorno. Registrá una app en "
                "https://developers.eveonline.com para obtenerlos."
            )
        pair = generate_pkce_pair()
        state = secrets.token_urlsafe(24)
        with self._oauth_pending_lock:
            self._cleanup_expired_oauth_state()
            self._oauth_pending[state] = (pair.code_verifier, frontend_redirect, time.time())

        return build_authorize_url(
            client_id=self.eve_sso_client.client_id, redirect_uri=redirect_uri,
            state=state, code_challenge=pair.code_challenge,
        )

    def _cleanup_expired_oauth_state(self) -> None:
        """Llamar siempre con `_oauth_pending_lock` ya tomado."""
        now = time.time()
        expired = [
            s for s, (_, _, created_at) in self._oauth_pending.items()
            if now - created_at > self.OAUTH_STATE_TTL_SECONDS
        ]
        for s in expired:
            del self._oauth_pending[s]

    def handle_eve_callback(self, code: str, state: str) -> Tuple[str, str]:
        """
        Procesa el callback de EVE SSO: valida el `state`, intercambia
        el `code` por tokens, identifica al personaje, crea/actualiza
        el usuario, guarda los tokens cifrados, y devuelve
        (session_token, frontend_redirect) -- el router usa el segundo
        para saber a dónde mandar de vuelta al browser.
        """
        if self.eve_sso_client is None:
            raise ValueError("EVE SSO no está configurado.")

        with self._oauth_pending_lock:
            pending = self._oauth_pending.pop(state, None)
        if pending is None:
            logger.warning("login_failed reason=invalid_or_expired_state state=%s", state[:8] + "...")
            raise ValueError(
                "El 'state' de este login es inválido o ya expiró (10 min de ventana) -- "
                "iniciá el login de nuevo desde el principio."
            )
        code_verifier, frontend_redirect, _ = pending

        try:
            token_response = self.eve_sso_client.exchange_code_for_token(code=code, code_verifier=code_verifier)
            identity = self.eve_sso_client.decode_character_identity(token_response.access_token)
        except EveSSOError as e:
            logger.error("login_failed reason=eve_sso_error detail=%s", str(e))
            raise

        user = self.user_repo.create_or_update_login(
            eve_character_id=identity.character_id,
            eve_character_name=identity.character_name,
        )

        self._store_oauth_tokens(user.id, token_response)

        logger.info(
            "login_success user_id=%s eve_character_id=%s eve_character_name=%s",
            user.id, user.eve_character_id, user.eve_character_name,
        )

        session_token = issue_session_token(user_id=user.id, eve_character_name=user.eve_character_name)
        return session_token, frontend_redirect

    def _get_token_encryptor(self) -> TokenEncryptor:
        if self._token_encryptor is None:
            self._token_encryptor = TokenEncryptor()
        return self._token_encryptor

    def _store_oauth_tokens(self, user_id: int, token_response) -> None:
        encryptor = self._get_token_encryptor()
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=token_response.expires_in)
        ).isoformat()

        conn = connect_db(self.db_path)
        conn.execute(
            "INSERT INTO oauth_tokens (user_id, access_token_encrypted, refresh_token_encrypted, expires_at, scopes) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "access_token_encrypted = excluded.access_token_encrypted, "
            "refresh_token_encrypted = excluded.refresh_token_encrypted, "
            "expires_at = excluded.expires_at",
            (
                user_id,
                encryptor.encrypt(token_response.access_token),
                encryptor.encrypt(token_response.refresh_token),
                expires_at,
                "",
            ),
        )
        conn.commit()
        conn.close()

    def get_user_from_session_token(self, token: str) -> User:
        """
        Levanta `SessionTokenError` si el token es inválido/expiró --
        el router debería traducir eso a un 401, no a un 500. Levanta
        `ValueError` si el usuario de la sesión ya no existe (caso
        raro, pero posible si se borró manualmente de la DB).
        """
        payload = verify_session_token(token)
        user = self.user_repo.get_by_id(payload["user_id"])
        if user is None:
            raise ValueError("El usuario de esta sesión ya no existe.")
        return user

    # ------------------------------------------------------------------
    # Observabilidad
    # ------------------------------------------------------------------

    def get_admin_stats(self) -> Dict[str, Any]:
        """
        Panorama básico del sistema -- pensado para cuando esto se
        comparta con la comunidad y haga falta una forma rápida de ver
        "¿cuánta gente lo está usando, hay algo roto?" sin tener que
        leer los archivos de log a mano. No requiere un rol de admin
        separado todavía (no existe ese concepto) -- ver limitación en
        el router.
        """
        conn = connect_db(self.db_path)
        conn.row_factory = sqlite3.Row

        total_users = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        total_tracked_items = conn.execute("SELECT COUNT(*) c FROM tracked_types").fetchone()["c"]
        users_with_watchlist = conn.execute(
            "SELECT COUNT(DISTINCT user_id) c FROM tracked_types"
        ).fetchone()["c"]
        recent_logins = conn.execute(
            "SELECT eve_character_name, last_login_at FROM users "
            "ORDER BY last_login_at DESC LIMIT 10"
        ).fetchall()

        conn.close()

        sync_status = self.get_sync_status()

        return {
            "total_users": total_users,
            "users_with_watchlist": users_with_watchlist,
            "total_tracked_items": total_tracked_items,
            "recent_logins": [
                {"eve_character_name": r["eve_character_name"], "last_login_at": r["last_login_at"]}
                for r in recent_logins
            ],
            "sync_status": sync_status,
        }
