---
title: "Soberanía de datos"
description: "Cómo la arquitectura autoalojada de Rediacc satisface los requisitos de residencia y soberanía de datos en jurisdicciones globales."
category: "Legal"
order: 7
language: es
sourceHash: "dba51d5d6dcf8197"
---

Muchos países requieren que los datos personales de sus ciudadanos se almacenen y procesen dentro de las fronteras nacionales. La arquitectura autoalojada de Rediacc satisface estos requisitos por diseño: los datos permanecen en tu máquina, en tu centro de datos, en tu jurisdicción. Ningún dato sale de la máquina durante la clonación, y ningún SaaS de terceros procesa tus datos.

## Por qué el autoalojamiento resuelve la soberanía de datos

La transferencia transfronteriza de datos es el problema de cumplimiento más difícil en la computación en la nube. Cada jurisdicción tiene reglas diferentes, decisiones de adecuación y mecanismos de transferencia. El autoalojamiento elimina toda la categoría:

- **Sin transferencia transfronteriza**: La clonación CoW (`cp --reflink=always`) duplica datos en la misma máquina
- **Sin procesador tercero**: Rediacc se ejecuta en tu infraestructura, no en los servidores de Rediacc
- **Sin evaluación de adecuación necesaria**: los datos nunca salen de la jurisdicción, por lo que las reglas de transferencia no aplican
- **Sin cláusulas contractuales estándar**: no hay flujo internacional de datos que regular

## Cobertura jurisdiccional

### Unión Europea

El [GDPR](https://gdpr-info.eu/) restringe las transferencias de datos personales fuera de la UE/EEA a menos que el destino proporcione protección adecuada. La sentencia Schrems II invalidó el Escudo de Privacidad UE-EE.UU., y la [multa de 1.200 M EUR contra Meta](https://www.dataprotection.ie/en/news-media/press-releases/Data-Protection-Commission-announces-conclusion-of-inquiry-into-Meta-Ireland) demostró el costo de errores en transferencias transfronterizas.

Rediacc autoalojado en la UE mantiene todos los datos dentro de la UE. No se necesita mecanismo de transferencia. Ver [Cumplimiento GDPR](/es/docs/legal-gdpr) para mapeo a nivel de artículos.

### China

La [PIPL](http://www.npc.gov.cn/npc/c30834/202108/a8c4e3672c74491a80b53a172bb753fe.shtml) requiere que los datos personales de ciudadanos chinos se almacenen en China. Las transferencias transfronterizas requieren evaluaciones de seguridad por la CAC. Rediacc autoalojado en infraestructura china evita las evaluaciones de seguridad de la CAC por completo.

### Brasil

La [LGPD](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm) requiere medidas de seguridad adecuadas y restringe las transferencias internacionales. El autoalojamiento en Brasil elimina las preocupaciones de transferencia y satisface el requisito del Art. 46 de medidas técnicas mediante cifrado LUKS2 y aislamiento de red.

### India

La [DPDP Act (2023)](https://www.meity.gov.in/content/digital-personal-data-protection-act-2023) restringe las transferencias a países no incluidos en una lista aprobada por el gobierno. El autoalojamiento en infraestructura india significa que no hay transferencia independientemente de qué países sean vetados. Los sectores gubernamental y de defensa de India prefieren fuertemente las soluciones locales.

### Turkiye

La [KVKK (Ley No. 6698)](https://kvkk.gov.tr/en/) restringe las transferencias internacionales con requisitos de adecuación complejos. Turkiye no está en la lista de adecuación de la UE, por lo que las transferencias transfronterizas requieren aprobación explícita. El autoalojamiento en Turkiye elimina esto por completo.

### Corea del Sur

La [PIPA](https://www.pipc.go.kr/eng/index.do) es una de las más estrictas del mundo y exige explícitamente el cifrado de datos personales durante el almacenamiento y la transmisión. LUKS2 AES-256 satisface directamente este requisito. Multas de hasta el 3% de los ingresos.

### Japón

La [APPI](https://www.ppc.go.jp/en/legal/) restringe las transferencias transfronterizas a menos que el país receptor proporcione protección adecuada. El autoalojamiento en Japón evita las restricciones de transferencia y se alinea con la preferencia cultural del mercado por soluciones locales.

### Australia

La [Privacy Act 1988](https://www.legislation.gov.au/C2004A03712/latest/text) responsabiliza a la entidad divulgadora por el manejo de datos del receptor extranjero (APP 8). El autoalojamiento elimina esta responsabilidad por completo. El cifrado LUKS2 y el aislamiento de red proporcionan "pasos razonables" concretos bajo APP 11.

### Emiratos Arabes Unidos

El [Decreto-Ley Federal No. 45/2021](https://u.ae/en/about-the-uae/digital-uae/data/data-protection-laws) requiere medidas de seguridad adecuadas y restringe las transferencias transfronterizas. Los sectores gubernamental y financiero de los EAU prefieren fuertemente los despliegues locales.

### Arabia Saudita

La [PDPL](https://sdaia.gov.sa/en/SDAIA/about/Documents/Personal%20Data%20English%20V2.pdf) requiere que los datos personales de residentes saudíes se almacenen y procesen dentro de Arabia Saudita. El autoalojamiento satisface directamente este estricto requisito de localización.

### Singapur

La [PDPA](https://sso.agc.gov.sg/Act/PDPA2012) requiere seguridad razonable y restringe las transferencias transfronterizas. El autoalojamiento en Singapur, un importante centro de datos en APAC, satisface el cumplimiento regional para operaciones de ASEAN.

### Rusia

La [Ley Federal 242-FZ](https://pd.rkn.gov.ru/) requiere que los datos personales de ciudadanos rusos se almacenen en servidores en Rusia. Las violaciones pueden resultar en bloqueo de sitios web. El autoalojamiento en suelo ruso proporciona cumplimiento por arquitectura.

## El patrón

En todas las jurisdicciones, la ecuación de cumplimiento es la misma:

| Propiedad | Nube/SaaS | Rediacc autoalojado |
|-----------|-----------|-------------------|
| Ubicación de datos | Centros de datos del proveedor (pueden cruzar fronteras) | Tu máquina, tu jurisdicción |
| Mecanismo de transferencia necesario | Sí (SCCs, adecuación, consentimiento) | No (no ocurre transferencia) |
| Responsabilidad del procesador tercero | Sí | No |
| Control de cifrado | Claves gestionadas por el proveedor | Tus credenciales LUKS, almacenadas localmente |
| Datos de clonación/staging | Pueden cruzar fronteras o salir de tu control | CoW en la misma máquina, misma jurisdicción |
