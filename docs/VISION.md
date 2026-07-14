# Quartermaster — Visión

> Documento de producto y filosofía, no de arquitectura técnica (para eso ver
> `ARCHITECTURE_V4_GENERIC_PLATFORM.md`, que ya venía ejecutando gran parte de lo que este
> documento formaliza). Escrito por el fundador el 13/07/2026. Cualquier decisión de
> arquitectura, RFC, o roadmap futuro debería poder contrastarse contra esto.

A partir de este momento, Quartermaster deja de pensarse como una aplicación para EVE Online.
Se piensa como una **empresa** y un **motor de inteligencia para la toma de decisiones**, donde
EVE Online es únicamente el primer caso de uso.

## Nueva visión

Quartermaster no existe para mostrar datos. Existe para transformar datos complejos en
conocimiento accionable. El objetivo es democratizar el acceso al análisis de datos para que
personas sin formación especializada puedan tomar mejores decisiones.

No queremos reemplazar al usuario. Queremos aumentar su capacidad de decisión.

## Problema que resolvemos

Vivimos en un mundo donde existe una enorme cantidad de datos, pero muy pocas personas tienen las
herramientas necesarias para interpretarlos correctamente. La información está democratizada. El
análisis no. Quartermaster busca cerrar esa brecha: transformar millones de datos en un resumen
comprensible, útil y accionable. No queremos producir más información. Queremos producir
comprensión.

## Nuestra definición de una buena decisión

Una buena decisión no es aquella que siempre termina siendo la más rentable. Una buena decisión
es aquella que, utilizando únicamente la información disponible en ese momento, logra una
asignación eficiente de los recursos mientras maximiza el valor esperado y controla adecuadamente
el riesgo.

El resultado futuro nunca puede garantizarse. La calidad del proceso sí. Quartermaster debe ayudar
a construir procesos de decisión consistentes y racionales.

## Principios del producto

Toda recomendación debe ser explicable. Toda puntuación debe justificarse. Todo análisis debe
poder rastrearse hasta los datos que lo originaron. Nunca debemos pedir confianza ciega.

La transparencia no es una característica adicional. Es un principio fundamental del sistema. Si
el usuario no puede entender por qué el sistema recomienda algo, entonces el sistema falló.

## Filosofía de inteligencia

Los datos por sí solos no tienen significado. El significado aparece cuando los datos se
interpretan dentro de un contexto. Quartermaster combina datos, contexto, modelos, reglas,
inferencias y explicaciones para producir inteligencia útil.

La explicabilidad debe formar parte del motor, no de la interfaz.

## Objetivo de experiencia de usuario

El usuario nunca debería sentirse abrumado. Debe abrir Quartermaster y comprender rápidamente:
qué está ocurriendo en el mercado, por qué está ocurriendo, cuáles son las mejores oportunidades,
cuáles son los principales riesgos, y cómo llegó el sistema a esas conclusiones.

El sistema debe resumir mercados complejos en conocimiento fácilmente consumible. El éxito no se
mide por la cantidad de métricas mostradas. Se mide por la claridad con la que el usuario entiende
el mercado.

## Visión de la empresa

Quartermaster es una empresa tecnológica, no una herramienta para EVE. La arquitectura debe
permitir que, en el futuro, el mismo motor pueda analizar cualquier mercado donde existan datos,
incertidumbre y decisiones económicas. EVE Online es únicamente el primer dominio.

El verdadero producto es **Quartermaster Engine**. Las aplicaciones para distintos mercados serán
clientes de ese motor.

---

## Nota de disciplina (agregada por continuidad de ingeniería, no parte del manifiesto original)

Este documento define el **norte**, no la **secuencia**. El riesgo real de esta visión no es
técnico -- los cinco motores de dominio ya son genéricos, ya no conocen EVE en su matemática. El
riesgo es de **secuencia**: diseñar la abstracción universal de "mercado" (`Venue`,
`MarketDataProvider`, `Strategy` como plugin) antes de tener un segundo proveedor de datos real es
la forma más común de fallar esta transición -- se termina generalizando el único caso conocido
(EVE) y llamándolo genérico sin haberlo probado contra nada distinto. Ver
`ARCHITECTURE_V4_GENERIC_PLATFORM.md` §5 y §8 para el detalle técnico de esta trampa específica, y
el roadmap por etapas (§7 del mismo documento) para la secuencia de bajo riesgo que sigue
sosteniendo esta visión sin comprometer lo que ya funciona para EVE.
