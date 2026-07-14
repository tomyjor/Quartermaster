"""
Domain Service: OpportunityEngine
Orquesta los motores analíticos (ROI, Liquidez, Riesgo, Competencia, Exit
Time) y compone el score final de una oportunidad. Formula version: log_v2.

--------------------------------------------------------------------------
ADDENDUM (post-Sprint 1): confiabilidad del precio + recomendación siempre visible
--------------------------------------------------------------------------
Dos ajustes sobre la clasificación, sin tocar la fórmula del score:

1. **`CAUTION_THIN_ORDER_BOOK`**: un ROI altísimo (miles de %) puede ser
   matemáticamente correcto y a la vez no confiable, si el mejor precio
   de compra y/o venta usado para calcularlo está sostenido por una sola
   orden. `liquidity_score` mide profundidad TOTAL del book, no si el
   precio puntual usado en el ROI es representativo -- son señales
   distintas. Ahora `_classify_recommendation` exige un mínimo de
   `MIN_ORDERS_PER_SIDE_FOR_PRICE_TRUST` órdenes de cada lado, y si no
   se cumple, lo dice explícitamente en vez de dejar que un ROI de
   4 dígitos se muestre sin ninguna advertencia.

2. **NEUTRAL ahora siempre se comunica**: antes, la categoría NEUTRAL no
   pintaba ningún badge en la UI (ver `_BADGE_STYLE` en
   `components/opportunity_table.py`), lo que dejaba al usuario sin
   saber si un ítem sin badge fue evaluado y resultó sin señal fuerte,
   o si algo se había salteado. Cada Opportunity ahora tiene una
   `recommendation_reason` pensada para mostrarse siempre, sea cual sea
   la categoría.

--------------------------------------------------------------------------
CHANGELOG log_v1 -> log_v2 (fix del bug de saturación reportado)
--------------------------------------------------------------------------
Síntoma reportado: ítems con ROI de 292%, 1558% y 3559% terminaban con
scores casi idénticos (~37.5) cuando tenían baja liquidez, y el badge
"Compra recomendada" podía activarse con liquidez casi nula.

Se identificaron y corrigieron TRES causas, no una sola:

1. **`roi_component` saturaba a partir de ~139% de ROI.**
   La fórmula anterior (`min(95, 35 + log10(roi) * 28)`) llegaba a su
   techo con cualquier ROI por encima de ~139%, así que 292%, 1558% y
   3559% caían todos en el mismo valor (95) -- literalmente no había
   forma de que el componente de ROI distinguiera entre "bueno" y
   "extraordinario" en el rango donde vive la mayoría de las
   oportunidades reales de Jita. `spread_quality` tenía el mismo problema
   (saturaba a partir de ~46% de spread). v2 usa un rango logarítmico
   mucho más ancho (ver `_roi_component` / `_spread_quality_component`)
   que sigue diferenciando incluso entre miles de % de ROI.

2. **El liquidity_score podía ser positivo con CERO evidencia de volumen
   real** ("order book fantasma"). Ver el changelog de
   `LiquidityEngine` (v1.4): antes, un ítem con `daily_volume=0` podía
   sacar hasta 40/100 de liquidez solo por tener mucho `volume_remain`
   estancado en el book. Esto es la causa más grave de las tres: hacía
   que la recomendación pudiera confiar en profundidad que nunca se
   mueve. Corregido en el motor de liquidez (media geométrica), no acá.

3. **El badge de recomendación vivía hardcodeado en la capa de
   presentación** (`app.py`), desincronizado del score real y sin
   acceso a la señal más importante (`daily_volume` crudo). Ahora
   `OpportunityEngine._classify_recommendation` es la única fuente de
   verdad: exige score alto, liquidity_score real Y evidencia de
   volumen diario simultáneamente. La UI solo lee el resultado.

Además, v2 rediseña la composición del score final: cada componente
(risk, liquidity, roi, competition, exit_time, spread) ahora vive en una
escala 0-100 propia, y los pesos (0.32 / 0.26 / 0.20 / 0.12 / 0.06 / 0.04,
igual que antes) se aplican de forma literal. Antes, "competition_factor"
y "exit_factor" no estaban en escala 0-100 (vivían en rangos como
0.50-1.40), así que la tabla de desglose mostrada al usuario decía
"peso 0.12" para un término que en la práctica contribuía como máximo
~3.2 puntos -- la tabla mentía sobre su propia matemática. Ahora
`score_breakdown["components"][x]["contribution"]` es exacto y la suma
de todas las contribuciones es, por construcción, igual a `final_score`
(ver `_build_score_breakdown`, que además expone ese chequeo como
`sum_of_contributions` para que sea auditable).
"""

import math
from dataclasses import dataclass
from typing import Dict, Tuple

from domain.value_objects.opportunity import Opportunity
from domain.value_objects.money import Money
from domain.value_objects.fee_profile import FeeProfile
from domain.value_objects.analysis_result import AnalysisResult
from domain.value_objects.risk import Risk
from domain.value_objects.liquidity import Liquidity
from domain.value_objects.competition import Competition
from domain.value_objects.exit_time import ExitTime
from domain.value_objects.recommendation import RecommendationLevel

from .roi_engine import ROIEngine, ROIInput
from .liquidity_engine import LiquidityEngine, LiquidityInput
from .risk_engine import RiskEngine, RiskInput
from .competition_engine import CompetitionEngine, CompetitionInput
from .exit_time_engine import ExitTimeEngine, ExitTimeInput


@dataclass(frozen=True)
class OpportunityInput:
    """Datos crudos de mercado necesarios para evaluar una oportunidad."""

    instrument_id: int
    instrument_name: str
    market_id: int
    buy_price: Money
    sell_price: Money
    daily_volume: float
    total_sell_volume_remain: float
    sell_order_count: int
    buy_order_count: int
    fee_profile: FeeProfile

    #: Suma de volume_remain de las órdenes de COMPRA activas. Default
    #: 0.0 por compatibilidad con callers existentes que todavía no lo
    #: proveen; en ese caso CompetitionEngine simplemente ve "sin
    #: evidencia de demanda", nunca inventa un número.
    total_buy_volume_remain: float = 0.0


class OpportunityEngine:
    """
    Motor de composición: agrega los resultados de los cinco motores
    analíticos puros en un único score explicable (0-100) y en una
    recomendación categórica. No contiene reglas de negocio propias más
    allá de "cómo pesar y combinar" lo que los otros motores ya
    calcularon -- toda regla de dominio nueva debería, en principio,
    vivir en su propio motor especializado, no acá.
    """

    # === Pesos de composición del score final (deben sumar 1.0) ===
    WEIGHT_RISK = 0.32
    WEIGHT_LIQUIDITY = 0.26
    WEIGHT_ROI = 0.20
    WEIGHT_COMPETITION = 0.12
    WEIGHT_EXIT_TIME = 0.06
    WEIGHT_SPREAD = 0.04

    # === Calibración de escalas logarítmicas (ver changelog del módulo) ===
    #: Puntos de score por cada orden de magnitud (10x) de crecimiento del ROI.
    ROI_LOG_SLOPE = 20.0
    #: Ídem para la calidad del spread bruto (señal secundaria/redundante).
    SPREAD_LOG_SLOPE = 18.0

    # === Calibración de Exit Time ===
    #: Horas a las que la favorabilidad del exit time cae a 50/100.
    EXIT_TIME_HALF_LIFE_HOURS = 24.0
    #: Piso del tamaño de posición de referencia -- nunca por debajo de
    #: esto, ni para ítems que se venden de a uno.
    DEFAULT_POSITION_SIZE = 100.0

    def _reference_position_size(self, input_data: "OpportunityInput") -> float:
        """
        Tamaño de posición de referencia para el tiempo de venta
        estimado -- ADAPTATIVO por ítem, no un número fijo para todos.

        Hallazgo real del usuario: usar siempre 100 unidades como
        referencia es sesgado para ítems que se comercian en bulk (ej.
        misiles, munición) -- 100 unidades de un misil no es una
        posición representativa. Sugirió dividir el volumen total
        vendido por la cantidad de vendedores para estimar un promedio
        diario "por vendedor". ESI no expone identidad de vendedor en
        el order book público, así que "por vendedor" exacto no es
        calculable -- se usa `sell_order_count` (cantidad de órdenes
        activas) como proxy.

        v2 -- bug propio encontrado corriendo los tests después del
        cambio: la primera versión dividía `total_sell_volume_remain`
        (STOCK listado ahora mismo) entre `sell_order_count`. Con una
        sola orden gigante (ej. alguien liquidando un stockpile de
        millones de unidades) esto disparaba la referencia a un tamaño
        absurdo -- un caso de test real dio 1.500.000 unidades de
        referencia contra un volumen diario de solo 20.000, un tiempo
        de venta de 75 días que no representa nada real. Cambiado a
        `daily_volume` (FLUJO real negociado por día) dividido por
        `sell_order_count` -- una sola orden atípica ya no puede
        distorsionar el resultado, porque el volumen diario es un
        agregado de trades reales, no de qué hay listado en este
        instante.

        `max(..., DEFAULT_POSITION_SIZE)`: nunca reduce la referencia
        por debajo del piso de siempre -- solo la sube para ítems que
        genuinamente mueven más por vendedor por día.
        """
        if input_data.sell_order_count <= 0 or input_data.daily_volume <= 0:
            return self.DEFAULT_POSITION_SIZE
        avg_daily_volume_per_seller = input_data.daily_volume / input_data.sell_order_count
        return max(avg_daily_volume_per_seller, self.DEFAULT_POSITION_SIZE)

    # === Umbrales de recomendación (única fuente de verdad del badge) ===
    RECOMMEND_MIN_SCORE = 65.0
    RECOMMEND_MIN_LIQUIDITY_SCORE = 15.0
    RECOMMEND_MIN_DAILY_VOLUME = 1.0
    CAUTION_LIQUIDITY_SCORE = 8.0
    CAUTION_RISK_SCORE = 70.0
    #: Mínimo de órdenes activas de CADA lado (compra y venta) para
    #: confiar en que el mejor precio no es una orden aislada/atípica.
    #: Con 1 sola orden de un lado, ese "mejor precio" (y por lo tanto
    #: el ROI calculado a partir de él) puede ser un troll, un error de
    #: tipeo, o una orden vieja sin cancelar -- no un precio de mercado
    #: real. Ver RecommendationLevel.CAUTION_THIN_ORDER_BOOK.
    MIN_ORDERS_PER_SIDE_FOR_PRICE_TRUST = 2

    #: Encontrado con datos reales: "Arch Angel Nuclear S" tenía 4
    #: órdenes de compra (mejor precio 1.1 ISK) y 19 de venta (mejor
    #: precio 78.69 ISK) -- spread de ~70x -- y pasaba el chequeo de
    #: MIN_ORDERS_PER_SIDE_FOR_PRICE_TRUST sin problema (4 >= 2), así
    #: que no se marcaba ninguna advertencia pese a ser, en la práctica,
    #: un mercado sin punto de encuentro real entre compradores y
    #: vendedores. El conteo de órdenes mide PROFUNDIDAD, no si esas
    #: órdenes están en el mismo rango de precio -- son chequeos
    #: distintos, hace falta el segundo además del primero. 5.0 = el
    #: precio de venta no debería superar 5x el de compra en un mercado
    #: que realmente está funcionando; por encima de eso, sugiere que
    #: vendedores y compradores casi no se están encontrando.
    MAX_PLAUSIBLE_SPREAD_RATIO = 5.0

    def __init__(self) -> None:
        self.roi_engine = ROIEngine()
        self.liquidity_engine = LiquidityEngine()
        self.risk_engine = RiskEngine()
        self.competition_engine = CompetitionEngine()
        self.exit_time_engine = ExitTimeEngine()

        weight_sum = (
            self.WEIGHT_RISK + self.WEIGHT_LIQUIDITY + self.WEIGHT_ROI +
            self.WEIGHT_COMPETITION + self.WEIGHT_EXIT_TIME + self.WEIGHT_SPREAD
        )
        assert abs(weight_sum - 1.0) < 1e-9, (
            f"Los pesos del score deben sumar 1.0, suman {weight_sum}"
        )

    def detect(self, input_data: OpportunityInput) -> AnalysisResult[Opportunity]:
        """Ejecuta los cinco motores analíticos y compone el score final."""

        roi_result = self.roi_engine.calculate(ROIInput(
            buy_price=input_data.buy_price,
            sell_price=input_data.sell_price,
            fee_profile=input_data.fee_profile,
        ))

        liquidity_result = self.liquidity_engine.calculate(LiquidityInput(
            daily_volume=input_data.daily_volume,
            total_sell_volume_remain=input_data.total_sell_volume_remain,
            sell_order_count=input_data.sell_order_count,
            buy_order_count=input_data.buy_order_count,
        ))

        # NOTA: CompetitionEngine v1.2 ya no acepta price_spread_percent
        # (se eliminó por señal invertida y redundante con roi/spread_quality
        # -- ver changelog en CompetitionEngine y MATH-003 v1.2).
        competition_result = self.competition_engine.calculate(CompetitionInput(
            buy_order_count=input_data.buy_order_count,
            sell_order_count=input_data.sell_order_count,
            total_buy_volume=input_data.total_buy_volume_remain,
            total_sell_volume=input_data.total_sell_volume_remain,
        ))

        risk_result = self.risk_engine.calculate(RiskInput(
            roi_percent=roi_result.value.roi_percent,
            liquidity=liquidity_result.value,
            competition_score=competition_result.value.competition_score,
            capital_required=roi_result.value.total_capital_required,
        ))

        reference_position_size = self._reference_position_size(input_data)
        exit_result = self.exit_time_engine.calculate(ExitTimeInput(
            position_size=reference_position_size,
            daily_volume=input_data.daily_volume,
            total_sell_volume_remain=input_data.total_sell_volume_remain,
        ))

        components: Dict[str, float] = {
            "risk": self._risk_component(risk_result.value),
            "liquidity": self._liquidity_component(liquidity_result.value),
            "roi": self._roi_component(roi_result.value.roi_percent),
            "competition": self._competition_component(competition_result.value),
            "exit_time": self._exit_time_component(exit_result.value),
            "spread": self._spread_quality_component(input_data.buy_price, input_data.sell_price),
        }
        weights = {
            "risk": self.WEIGHT_RISK,
            "liquidity": self.WEIGHT_LIQUIDITY,
            "roi": self.WEIGHT_ROI,
            "competition": self.WEIGHT_COMPETITION,
            "exit_time": self.WEIGHT_EXIT_TIME,
            "spread": self.WEIGHT_SPREAD,
        }

        opportunity_score = sum(components[k] * weights[k] for k in components)
        opportunity_score = round(min(max(opportunity_score, 0.0), 100.0), 2)

        recommendation, recommendation_reason = self._classify_recommendation(
            score=opportunity_score,
            liquidity=liquidity_result.value,
            risk=risk_result.value,
            sell_order_count=input_data.sell_order_count,
            buy_order_count=input_data.buy_order_count,
            roi_percent=roi_result.value.roi_percent,
            buy_price=input_data.buy_price,
            sell_price=input_data.sell_price,
        )

        score_breakdown = self._build_score_breakdown(components, weights, opportunity_score)
        score_breakdown["recommendation"] = recommendation.value
        score_breakdown["recommendation_reason"] = recommendation_reason
        score_breakdown["has_volume_evidence"] = input_data.daily_volume > 0

        opportunity = Opportunity(
            instrument_id=input_data.instrument_id,
            instrument_name=input_data.instrument_name,
            market_id=input_data.market_id,
            buy_price=input_data.buy_price,
            sell_price=input_data.sell_price,
            roi_percent=roi_result.value.roi_percent,
            liquidity=liquidity_result.value,
            risk=risk_result.value,
            score=opportunity_score,
            score_breakdown=score_breakdown,
            recommendation=recommendation,
            recommendation_reason=recommendation_reason,
            sell_order_count=input_data.sell_order_count,
            buy_order_count=input_data.buy_order_count,
            estimated_exit_hours=exit_result.value.estimated_hours,
            estimated_exit_position_size=reference_position_size,
        )

        overall_confidence = min(
            roi_result.confidence,
            liquidity_result.confidence,
            risk_result.confidence,
            competition_result.confidence,
            exit_result.confidence,
        )
        # Si algún motor degradó su validación (típicamente liquidez sin
        # evidencia de volumen), la Opportunity completa hereda ese estado
        # -- no tiene sentido reportar "Valid" si uno de los insumos no lo es.
        overall_status = (
            "Degraded"
            if liquidity_result.validation_status == "Degraded"
            else "Valid"
        )

        return AnalysisResult(
            value=opportunity,
            confidence=overall_confidence,
            evidence_count=5,
            validation_status=overall_status,
        )

    # ------------------------------------------------------------------
    # Componentes individuales del score (cada uno normalizado a 0-100)
    # ------------------------------------------------------------------

    def _risk_component(self, risk: Risk) -> float:
        """Favorabilidad de riesgo, 0-100 (100 = sin riesgo detectado)."""
        return max(0.0, 100.0 - risk.overall_risk_score)

    def _liquidity_component(self, liquidity: Liquidity) -> float:
        """Liquidez real, 0-100. Ya viene gateada por turnover real (MATH-002 v1.4)."""
        return liquidity.liquidity_score

    def _roi_component(self, roi_percent: float) -> float:
        """
        ROI en escala logarítmica, 0-100.

        Escala en base 10: cada orden de magnitud (10x) de ROI suma
        `ROI_LOG_SLOPE` puntos. A diferencia de la versión anterior (que
        saturaba a partir de ~139% de ROI porque el rango elegido era
        demasiado angosto), este rango sigue diferenciando de forma
        significativa incluso entre ROIs de cientos y miles de por
        ciento -- el caso reportado (292% / 1558% / 3559% con la misma
        liquidez) ya no colapsa al mismo valor.
        """
        roi_clamped = max(0.0, roi_percent)
        raw = self.ROI_LOG_SLOPE * math.log10(1.0 + roi_clamped)
        return min(100.0, raw)

    def _spread_quality_component(self, buy_price: Money, sell_price: Money) -> float:
        """
        Calidad del spread bruto (antes de fees), 0-100.

        Misma familia de escala logarítmica que `_roi_component`, pero
        con menor peso en el score final -- es una señal redundante con
        el ROI neto (ambas derivan del mismo spread), útil sobre todo
        como sanity check visual independiente de la fiscalidad asumida.

        Si no hay spread positivo real (datos incompletos o inválidos),
        devuelve 0.0 explícito -- no se inventa un valor "neutral" de
        relleno, consistente con el resto del proyecto (ver
        `SQLiteMarketRepository`).
        """
        buy = buy_price.amount
        sell = sell_price.amount
        if buy <= 0 or sell <= buy:
            return 0.0
        spread_pct = ((sell - buy) / buy) * 100
        raw = self.SPREAD_LOG_SLOPE * math.log10(1.0 + spread_pct)
        return min(100.0, raw)

    def _competition_component(self, competition: Competition) -> float:
        """Favorabilidad competitiva, 0-100 (100 = sin competencia detectada)."""
        return max(0.0, 100.0 - competition.competition_score)

    def _exit_time_component(self, exit_time: ExitTime) -> float:
        """
        Favorabilidad del tiempo de salida estimado, 0-100.

        Decaimiento hiperbólico suave: 100 en t=0, 50 a las
        `EXIT_TIME_HALF_LIFE_HOURS`, y tiende a 0 sin necesitar un tope
        artificial ni volverse negativo.
        """
        hours = max(0.0, exit_time.estimated_hours)
        return 100.0 / (1.0 + (hours / self.EXIT_TIME_HALF_LIFE_HOURS))

    # ------------------------------------------------------------------
    # Recomendación (única fuente de verdad para el badge de la UI)
    # ------------------------------------------------------------------

    def _classify_recommendation(
        self,
        score: float,
        liquidity: Liquidity,
        risk: Risk,
        sell_order_count: int,
        buy_order_count: int,
        roi_percent: float,
        buy_price: Money,
        sell_price: Money,
    ) -> Tuple[RecommendationLevel, str]:
        """
        Determina la recomendación final para una Opportunity ya scoreada.

        Esta es la ÚNICA fuente de verdad para "¿es seguro recomendar esta
        compra?". La capa de presentación debe leer el resultado, nunca
        reimplementar estos umbrales con sus propios números hardcodeados
        -- ese acoplamiento fue el origen del bug de items con order book
        fantasma marcados como "Compra recomendada".

        SIEMPRE devuelve una categoría explícita, incluso NEUTRAL -- nunca
        "nada que mostrar". Antes, NEUTRAL no pintaba ningún badge en la
        UI, lo que dejaba al usuario sin saber si el ítem fue evaluado
        (y resultó sin señal fuerte) o si algo se había salteado.

        v1.1: BUY ahora exige explícitamente `roi_percent > 0`. Antes el
        gate no lo chequeaba -- roi_component usa
        `max(0, roi_percent)`, así que un ROI negativo contribuye 0 al
        score, pero NADA impedía que buena liquidez/riesgo/competencia
        igual empujaran el score por encima de 65 sin ROI positivo real.
        No se vio en la práctica (los ejemplos con ROI negativo no
        llegaban a 65), pero era un hueco real, no una garantía --
        comprar y revender con ROI negativo es perder plata, sin
        importar cuán líquido o poco riesgoso sea el ítem.
        """
        has_volume_evidence = liquidity.daily_volume > 0
        has_thin_order_book = (
            sell_order_count < self.MIN_ORDERS_PER_SIDE_FOR_PRICE_TRUST
            or buy_order_count < self.MIN_ORDERS_PER_SIDE_FOR_PRICE_TRUST
        )
        # Chequeo INDEPENDIENTE del anterior: puede haber suficientes
        # órdenes de cada lado y AUN ASÍ que compradores y vendedores
        # estén en mundos de precio completamente distintos (ver
        # MAX_PLAUSIBLE_SPREAD_RATIO). buy_price.amount_minor > 0 evita
        # división por cero -- ya validado antes en ROIEngine, pero acá
        # es un chequeo aparte, mejor no asumir.
        has_implausible_spread = (
            buy_price.amount_minor > 0
            and (sell_price.amount_minor / buy_price.amount_minor) > self.MAX_PLAUSIBLE_SPREAD_RATIO
        )

        if (
            score >= self.RECOMMEND_MIN_SCORE
            and liquidity.liquidity_score >= self.RECOMMEND_MIN_LIQUIDITY_SCORE
            and has_volume_evidence
            and liquidity.daily_volume >= self.RECOMMEND_MIN_DAILY_VOLUME
            and not has_thin_order_book
            and not has_implausible_spread
            and roi_percent > 0
        ):
            return (
                RecommendationLevel.BUY,
                "Buena combinación de ROI, riesgo y liquidez real verificada "
                f"(score {score:.1f}, liquidez {liquidity.liquidity_score:.1f}/100, "
                f"volumen diario real {liquidity.daily_volume:.0f} unidades, precio "
                f"respaldado por {sell_order_count} órdenes de venta y "
                f"{buy_order_count} de compra).",
            )

        # Chequeo de confiabilidad del PRECIO en sí (independiente de la
        # liquidez agregada): si el mejor precio de compra o de venta
        # está sostenido por muy pocas órdenes, el ROI calculado sobre
        # ese precio no es representativo de un mercado real, sin
        # importar cuán bueno se vea el resto del score.
        if has_thin_order_book:
            return (
                RecommendationLevel.CAUTION_THIN_ORDER_BOOK,
                "El precio de compra y/o venta usado para este ROI está respaldado por "
                f"muy pocas órdenes activas ({sell_order_count} de venta, {buy_order_count} "
                "de compra) -- puede tratarse de una orden aislada, un error de tipeo, o una "
                "orden vieja sin cancelar. Un ROI calculado sobre un precio así no es "
                "confiable: verificalo manualmente en el juego antes de operar.",
            )

        # Segundo chequeo de confiabilidad del precio, distinto al de
        # arriba: acá SÍ hay suficientes órdenes de cada lado, pero el
        # precio de venta está a un múltiplo implausible del de compra
        # -- síntoma de que ninguna de esas órdenes va a cruzarse con la
        # otra en la práctica, aunque el conteo se vea saludable.
        #
        # Va DESPUÉS del chequeo de volumen a propósito: si ni siquiera
        # hay evidencia de que el ítem se comercia (has_volume_evidence
        # False), eso es un problema más fundamental que la coherencia
        # del spread puntual -- no tiene sentido analizar si el spread
        # "tiene sentido" en un ítem del que no sabemos si se mueve.
        if not has_volume_evidence:
            return (
                RecommendationLevel.CAUTION_NO_VOLUME_DATA,
                "Sin evidencia de volumen diario negociado (market_history vacío "
                "o ítem sin trades reales recientes). No se puede confirmar "
                "liquidez real: posible order book fantasma. Importá el "
                "historial de volumen antes de operar.",
            )

        if has_implausible_spread:
            ratio = sell_price.amount_minor / buy_price.amount_minor
            return (
                RecommendationLevel.CAUTION_IMPLAUSIBLE_SPREAD,
                f"El precio de venta es {ratio:.0f}x el de compra (Buy: {buy_price.amount:.2f} "
                f"ISK, Sell: {sell_price.amount:.2f} ISK) pese a tener suficientes órdenes de "
                "cada lado -- compradores y vendedores parecen estar en rangos de precio "
                "completamente distintos, no un mercado con punto de encuentro real. El ROI "
                "calculado sobre este spread probablemente no sea ejecutable tal cual se muestra.",
            )

        if liquidity.liquidity_score < self.CAUTION_LIQUIDITY_SCORE:
            return (
                RecommendationLevel.CAUTION_LOW_LIQUIDITY,
                f"Liquidez muy baja ({liquidity.liquidity_score:.1f}/100) pese a "
                "tener algo de volumen registrado. Alto riesgo de no poder "
                "salir de la posición al precio esperado. Verificar manualmente.",
            )

        if risk.overall_risk_score > self.CAUTION_RISK_SCORE:
            return (
                RecommendationLevel.CAUTION_HIGH_RISK,
                f"Riesgo alto ({risk.overall_risk_score:.1f}/100) — revisar con "
                "cuidado antes de operar.",
            )

        return (
            RecommendationLevel.NEUTRAL,
            f"Oportunidad dentro de rango normal (score {score:.1f}): ni particularmente "
            "buena ni particularmente riesgosa según los motores. No hay señales fuertes "
            "en ningún sentido -- es una decisión de juicio, no un caso claro.",
        )

    # ------------------------------------------------------------------
    # Transparencia del cálculo
    # ------------------------------------------------------------------

    def _build_score_breakdown(
        self,
        components: Dict[str, float],
        weights: Dict[str, float],
        final_score: float,
    ) -> Dict:
        """
        Construye el desglose completo y auditable del score.

        `components[x]["contribution"]` es literalmente `raw_value * weight`
        para cada componente, y la suma de todas las contribuciones
        (`sum_of_contributions`) coincide con `final_score` salvo por
        redondeo de centésimas. Esto reemplaza la tabla anterior, que
        mostraba pesos que no correspondían a la contribución real de
        `competition_factor` y `exit_factor` (ver changelog del módulo).
        """
        labels = {
            "risk": "Riesgo (100 − riesgo total)",
            "liquidity": "Liquidez real (turnover verificado)",
            "roi": "ROI (escala logarítmica)",
            "competition": "Competencia (100 − presión competitiva)",
            "exit_time": "Tiempo de salida estimado",
            "spread": "Calidad del spread (escala logarítmica)",
        }

        breakdown_components = {}
        running_total = 0.0
        for key, raw_value in components.items():
            weight = weights[key]
            contribution = round(raw_value * weight, 2)
            running_total += contribution
            breakdown_components[key] = {
                "label": labels[key],
                "raw_value": round(raw_value, 2),
                "weight": weight,
                "contribution": contribution,
            }

        return {
            "formula_version": "log_v2",
            "components": breakdown_components,
            "final_score": round(final_score, 2),
            # Chequeo de honestidad: si esto difiere de final_score en más
            # que un margen de redondeo, hay un bug en la composición.
            "sum_of_contributions": round(running_total, 2),
        }
