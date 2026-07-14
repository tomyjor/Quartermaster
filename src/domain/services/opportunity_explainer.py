"""
Domain Service: OpportunityExplainer

Genera explicaciones legibles para humanos a partir de una `Opportunity`
YA calculada por `OpportunityEngine`. No decide ningún número -- solo
interpreta los que ya existen (`score_breakdown`, `liquidity`, `risk`,
`roi_percent`, `estimated_exit_hours`, conteos de órdenes) y los traduce
a texto específico del ítem analizado.

Principio de diseño (mismo que el resto del dominio): CERO texto
genérico. Cada frase se construye insertando los números reales de ESA
oportunidad puntual -- dos ítems con liquidez distinta reciben
explicaciones de liquidez distintas, no la misma plantilla con el
número cambiado al final.

Vive en `domain/services/` junto a los otros motores porque interpretar
"qué significa liquidez=38" es conocimiento de dominio (qué es alta,
media o baja liquidez, qué implica para ejecución y slippage), no una
decisión de presentación -- la UI solo pinta el texto que este servicio
ya armó, igual que hace con `recommendation_reason` de OpportunityEngine.

Separado de `OpportunityEngine` a propósito: el engine decide el score
(matemática, RFC MATH-00X), este servicio interpreta un resultado ya
cerrado. Mezclar ambas responsabilidades en una sola clase hubiera
hecho `OpportunityEngine` más difícil de testear y de razonar --
mismo principio de Single Responsibility que ya separa ROIEngine de
LiquidityEngine.
"""

from dataclasses import dataclass
from typing import List, Dict, Any

from domain.value_objects.opportunity import Opportunity
from domain.value_objects.risk import Risk
from domain.value_objects.liquidity import Liquidity


@dataclass(frozen=True)
class Explanation:
    """
    Explicación completa de una Opportunity, lista para que la UI la
    pinte dentro de un panel expandible -- ver `OpportunityExplainer`.
    """
    summary: str
    strengths: List[str]
    weaknesses: List[str]
    neutral_factors: List[str]
    liquidity_interpretation: str
    risk_interpretation: str
    insights: List[str]


class OpportunityExplainer:
    """
    Clasifica cada componente del score en fortaleza/debilidad/neutro
    usando los mismos umbrales para todo el sistema, e interpreta en
    profundidad liquidez y riesgo (los dos conceptos que más piden
    contexto para alguien sin teoría de mercados).
    """

    #: raw_value (0-100) de un componente a partir del cual se considera
    #: una fortaleza real, no una mención al pasar.
    STRENGTH_THRESHOLD = 70.0

    #: por debajo de esto, se considera una debilidad real que vale la
    #: pena nombrar explícitamente.
    WEAKNESS_THRESHOLD = 40.0

    def explain(self, opportunity: Opportunity) -> Explanation:
        components: Dict[str, Any] = opportunity.score_breakdown.get("components", {})
        strengths, weaknesses, neutral = self._classify_components(components, opportunity)

        return Explanation(
            summary=self._build_summary(opportunity, strengths, weaknesses),
            strengths=strengths,
            weaknesses=weaknesses,
            neutral_factors=neutral,
            liquidity_interpretation=self._interpret_liquidity(opportunity),
            risk_interpretation=self._interpret_risk(opportunity),
            insights=self._generate_insights(opportunity),
        )

    # ------------------------------------------------------------------
    # Clasificación de componentes del score
    # ------------------------------------------------------------------

    def _classify_components(self, components: Dict[str, Any], o: Opportunity):
        describers = {
            "risk": self._describe_risk_component,
            "liquidity": self._describe_liquidity_component,
            "roi": self._describe_roi_component,
            "competition": self._describe_competition_component,
            "exit_time": self._describe_exit_time_component,
            "spread": self._describe_spread_component,
        }
        strengths, weaknesses, neutral = [], [], []
        for key, comp in components.items():
            raw = comp["raw_value"]
            describer = describers.get(key)
            text = describer(raw, o) if describer else f"{comp['label']}: {raw:.0f}/100."
            if raw >= self.STRENGTH_THRESHOLD:
                strengths.append(text)
            elif raw < self.WEAKNESS_THRESHOLD:
                weaknesses.append(text)
            else:
                neutral.append(text)
        return strengths, weaknesses, neutral

    def _describe_risk_component(self, raw: float, o: Opportunity) -> str:
        risk = o.risk
        if raw >= self.STRENGTH_THRESHOLD:
            return (
                f"Riesgo controlado: nivel {risk.risk_level} "
                f"(score de riesgo {risk.overall_risk_score:.0f}/100, más bajo es mejor)."
            )
        detail = self._worst_risk_subcomponent(risk)
        return (
            f"Riesgo {risk.risk_level.lower()} (score {risk.overall_risk_score:.0f}/100)."
            + (f" {detail}" if detail else "")
        )

    def _worst_risk_subcomponent(self, risk: Risk) -> str:
        if not risk.components:
            return ""
        worst_key, worst_val = max(risk.components.items(), key=lambda kv: kv[1])
        return f"El factor que más pesa es '{worst_key}' ({worst_val:.0f}/100)."

    def _describe_liquidity_component(self, raw: float, o: Opportunity) -> str:
        liq = o.liquidity
        if raw >= self.STRENGTH_THRESHOLD:
            return (
                f"Liquidez real verificada ({raw:.0f}/100), con volumen diario de "
                f"{liq.daily_volume:,.0f} unidades -- entrar y salir de la posición debería "
                "ser rápido."
            )
        if liq.daily_volume <= 0:
            return "Sin ningún día de volumen histórico registrado -- liquidez tratada como desconocida, no como cero confirmado."
        return (
            f"Liquidez limitada ({raw:.0f}/100) pese a {liq.daily_volume:,.0f} unidades de "
            "volumen diario -- puede haber poca profundidad real detrás del mejor precio."
        )

    def _describe_roi_component(self, raw: float, o: Opportunity) -> str:
        return f"ROI de {o.roi_percent:.1f}% (componente normalizado: {raw:.0f}/100 en escala logarítmica)."

    def _describe_competition_component(self, raw: float, o: Opportunity) -> str:
        if raw >= self.STRENGTH_THRESHOLD:
            return f"Baja presión competitiva ({raw:.0f}/100 de favorabilidad) -- pocos jugadores disputando el margen."
        return (
            f"Competencia significativa (favorabilidad {raw:.0f}/100) -- el margen puede "
            "erosionarse rápido si otros traders reaccionan al mismo precio."
        )

    def _describe_exit_time_component(self, raw: float, o: Opportunity) -> str:
        from shared.eta import format_duration_hours
        human = format_duration_hours(o.estimated_exit_hours) or "desconocido"
        ref_size = f"{o.estimated_exit_position_size:,.0f}"
        if raw >= self.STRENGTH_THRESHOLD:
            return f"Salida rápida esperada: {human} para una posición de referencia de {ref_size} unidades."
        return f"Salida lenta esperada: {human} para una posición de referencia de {ref_size} unidades -- pensalo como posición de mediano plazo, no un flip rápido."

    def _describe_spread_component(self, raw: float, o: Opportunity) -> str:
        spread_pct = ((o.sell_price.amount - o.buy_price.amount) / o.buy_price.amount * 100) if o.buy_price.amount else 0.0
        if raw >= self.STRENGTH_THRESHOLD:
            if spread_pct > 200:
                # El componente normalizado (log-scaled) trata cualquier
                # spread grande como favorable para el ROI, pero un
                # spread así de amplio suele ser señal de mercado fino
                # o precio atípico -- no algo genuinamente "sano".
                # Encontrado testeando contra datos reales (ítems con
                # spreads de miles de %): sin este chequeo, la
                # explicación llamaba "saludable" a un spread de 12150%.
                return (
                    f"Spread muy amplio (~{spread_pct:.0f}%) -- matemáticamente favorece el ROI, "
                    "pero un spread así de grande suele indicar un mercado fino o un precio "
                    "atípico, no necesariamente una buena señal por sí sola."
                )
            return f"Spread saludable (~{spread_pct:.1f}% entre compra y venta)."
        return f"Spread ajustado (~{spread_pct:.1f}%) -- poco margen de maniobra frente a fees y movimientos de precio."

    # ------------------------------------------------------------------
    # Interpretación en profundidad: liquidez
    # ------------------------------------------------------------------

    def _interpret_liquidity(self, o: Opportunity) -> str:
        liq: Liquidity = o.liquidity
        score = liq.liquidity_score

        if score >= 80:
            band = "alta"
            speed = "rápida: las órdenes de este ítem suelen llenarse en minutos, no en horas"
            slippage = "bajo -- hay profundidad suficiente en ambos lados para mover una posición sin desplazar mucho el precio"
            fit = "Conviene para trading frecuente y rotación rápida de capital."
        elif score >= 50:
            band = "media"
            speed = "moderada: desde minutos hasta unas horas según el tamaño de la orden"
            slippage = "moderado -- posiciones grandes pueden necesitar escalonarse en varias órdenes"
            fit = "Funciona tanto para rotación rápida como para posiciones algo más largas."
        elif score > 0:
            band = "baja"
            speed = "lenta: podés esperar horas o incluso días para llenar una orden completa"
            slippage = "alto -- cualquier posición de tamaño considerable va a mover el precio en contra al ejecutarse"
            fit = "Más apta para posiciones de mayor duración que para rotación rápida; entrar y salir rápido puede salir caro."
        else:
            band = "inexistente o sin evidencia"
            speed = "no estimable -- no hay datos de volumen reciente"
            slippage = "desconocido -- sin volumen no hay forma de estimarlo con confianza"
            fit = "No recomendable para trading activo con la información disponible hoy."

        volume_txt = (
            f"volumen diario promedio de {liq.daily_volume:,.0f} unidades"
            if liq.daily_volume > 0
            else "sin ningún día de volumen histórico importado todavía"
        )
        book_txt = f"El order book tiene {o.sell_order_count} órdenes de venta y {o.buy_order_count} de compra activas."
        depth_txt = f"Profundidad del book: {liq.depth_score:.0f}/100."
        regional_caveat = (
            "⚠️ Ese volumen es de TODA la región (La Forge), no solo de Jita 4-4 -- "
            "ESI no entrega historial por estación. Si este ítem se comercia mucho en otras "
            "estaciones de la región, el volumen puede estar sobreestimado respecto a lo que "
            "realmente rota en Jita, donde están tus órdenes. La profundidad del book (arriba) "
            "sí es específica de Jita."
        ) if liq.daily_volume > 0 else ""

        return (
            f"Liquidez {band} ({score:.0f}/100), con {volume_txt}. {book_txt} {depth_txt} "
            f"Velocidad de ejecución esperada: {speed}. Riesgo de slippage: {slippage}. {fit}"
            + (f" {regional_caveat}" if regional_caveat else "")
        )

    # ------------------------------------------------------------------
    # Interpretación en profundidad: riesgo
    # ------------------------------------------------------------------

    def _interpret_risk(self, o: Opportunity) -> str:
        risk = o.risk
        parts = [
            f"Nivel de riesgo: {risk.risk_level} (score {risk.overall_risk_score:.0f}/100, "
            "donde más alto significa más riesgoso)."
        ]
        if risk.components:
            ranked = sorted(risk.components.items(), key=lambda kv: -kv[1])
            top_key, top_val = ranked[0]
            parts.append(f"El factor que más contribuye al riesgo es '{top_key}' ({top_val:.0f}/100).")
            if len(ranked) > 1:
                second_key, second_val = ranked[1]
                parts.append(f"Le sigue '{second_key}' ({second_val:.0f}/100).")
        return " ".join(parts)

    # ------------------------------------------------------------------
    # Insights combinados (no por-componente, sino cruzando señales)
    # ------------------------------------------------------------------

    def _generate_insights(self, o: Opportunity) -> List[str]:
        insights = []
        liq = o.liquidity
        risk = o.risk

        if liq.liquidity_score >= 70 and o.roi_percent < 15:
            insights.append(
                "Mercado muy líquido pero con margen ajustado -- más apto para volumen "
                "operado que para margen alto por operación individual."
            )
        if liq.liquidity_score < 40 and o.roi_percent > 50:
            insights.append(
                f"ROI llamativo ({o.roi_percent:.1f}%) combinado con liquidez baja -- "
                "verificá manualmente en el juego antes de comprometer capital, el spread "
                "mostrado puede no ser ejecutable en la práctica."
            )
        if o.sell_order_count <= 3 or o.buy_order_count <= 3:
            insights.append(
                "Order book fino (pocas órdenes de al menos un lado) -- el precio mostrado "
                "puede no sostenerse si intentás operar un volumen mayor al de esas pocas órdenes."
            )
        if risk.risk_level == "Low" and liq.liquidity_score >= 60:
            insights.append("Buena relación riesgo/liquidez -- candidato razonable para trading activo.")
        if o.estimated_exit_hours > 24:
            from shared.eta import format_duration_hours
            human = format_duration_hours(o.estimated_exit_hours)
            insights.append(
                f"El tiempo estimado de salida ({human} para una posición de referencia) "
                "sugiere pensarlo como posición de mediano plazo, no como flip rápido."
            )
        if risk.risk_level in ("High", "Critical") and o.roi_percent < 20:
            insights.append(
                "Riesgo alto sin una prima de ROI que lo compense claramente -- "
                "la relación riesgo/retorno no parece favorable acá."
            )

        if not insights:
            insights.append(
                "Sin señales combinadas particularmente fuertes en ningún sentido -- "
                "es una oportunidad dentro de rango normal, la decisión queda en tu criterio."
            )
        return insights

    # ------------------------------------------------------------------
    # Resumen ejecutivo
    # ------------------------------------------------------------------

    def _build_summary(self, o: Opportunity, strengths: List[str], weaknesses: List[str]) -> str:
        if len(strengths) > len(weaknesses) and o.score >= 65:
            driver = strengths[0]
            return f"El score final ({o.score:.1f}) es elevado principalmente por: {driver}"
        if len(weaknesses) > len(strengths):
            driver = weaknesses[0]
            return f"El score final ({o.score:.1f}) se ve limitado principalmente por: {driver}"
        return (
            f"El score final ({o.score:.1f}) refleja un balance entre señales positivas y "
            "negativas -- no hay un factor dominante único, vale la pena mirar el desglose completo."
        )
