---
title: "Lo que el cumplimiento realmente requiere"
description: "Rediacc se ejecuta en tu infraestructura. Controlas tus datos. Aquí te mostramos cómo se alinea con los principales marcos de cumplimiento."
category: "Legal"
order: 0
language: es
sourceHash: "e6044a3b067b54d5"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

Rediacc se ejecuta completamente en tu infraestructura. Durante las operaciones de clonación, respaldo y despliegue, tus datos permanecen en tus máquinas. Eres tanto el controlador como el procesador de datos. Sin SaaS de terceros, sin acceso externo.

Mapeamos las capacidades técnicas de Rediacc a los requisitos de los principales marcos de cumplimiento. Cada página desglosa una regulación específica con referencias a los textos legales oficiales.

## Matriz de cumplimiento

| Marco | Alcance | Capacidades clave de Rediacc |
|-------|---------|------------------------------|
| [GDPR](/es/docs/legal-gdpr) | Protección de datos y privacidad de la UE | Clonación CoW en la misma máquina, cifrado LUKS2, almacén de configuración de conocimiento cero, registro de auditoría, derecho al olvido vía `rdc repo delete` |
| [SOC 2](/es/docs/legal-soc2) | Criterios de servicio de confianza para organizaciones de servicios | Cifrado en reposo, sincronización de configuración de conocimiento cero, aislamiento de red, registro de auditoría, respaldo y recuperación |
| [HIPAA](/es/docs/legal-hipaa) | Protección de información de salud en EE.UU. | Cifrado LUKS2, almacén de configuración de conocimiento cero, acceso solo por SSH, Docker daemons aislados, seguridad de transmisión |
| [CCPA](/es/docs/legal-ccpa) | Derechos de privacidad del consumidor de California | Autoalojado (sin venta/compartición de datos), cifrado de conocimiento cero, eliminación cifrada, inventario de datos por repositorio |
| [ISO 27001](/es/docs/legal-iso27001) | Controles de gestión de seguridad de la información | Gestión de activos, controles criptográficos, almacén de configuración de conocimiento cero, control de acceso, seguridad operativa |
| [PCI DSS](/es/docs/legal-pci-dss) | Protección de datos de tarjetas de pago | Segmentación de red por arquitectura, cifrado obligatorio, registro de auditoría, reducción de alcance mediante autoalojamiento |
| [NIS2 y DORA](/es/docs/legal-nis2-dora) | Ciberseguridad y resiliencia financiera de la UE | Eliminación de riesgos en la cadena de suministro, pruebas de resiliencia vía clonación CoW, cifrado, detección de incidentes |
| [Soberanía de datos](/es/docs/legal-data-sovereignty) | Leyes globales de residencia de datos (PIPL, LGPD, KVKK, PIPA y más) | Autoalojado = los datos nunca salen de tu jurisdicción. Sin transferencias transfronterizas, sin evaluaciones de adecuación |

## Fundamentos arquitectónicos

Aquí está lo que los conecta todos: cada marco de cumplimiento en esta sección se remite a los mismos fundamentos técnicos.

- **Cifrado en reposo**: Cada repositorio está cifrado con LUKS2 AES-256. Las credenciales se almacenan solo en la configuración local del operador, nunca en el servidor.
- **Aislamiento de red**: Cada repositorio obtiene su propio Docker daemon, subred de IP loopback (/26) y reglas de iptables. Los contenedores de diferentes repositorios no pueden comunicarse entre sí.
- **Clonación copy-on-write**: `rdc repo fork` utiliza reflinks del sistema de archivos (`cp --reflink=always`). Los datos se duplican en la misma máquina sin ninguna transferencia de red.
- **Registro de auditoría**: Más de 70 tipos de eventos que cubren autenticación (inicio de sesión, 2FA, cambios de contraseña, revocación de sesiones), ciclo de vida de tokens API, operaciones del almacén de configuración, actividad de suscripción/licencias y operaciones de máquina CLI (ciclo de vida de repositorio, respaldo, sincronización, sesiones de terminal). Accesible a través del panel de administración y la página de actividad del portal (con filtrado por ámbito de organización y exportación JSON). Las operaciones de máquina también se registran en tus registros del sistema para defensa en profundidad.
- **Respaldo cifrado**: `rdc repo push/pull` transfiere datos por SSH. El destino de respaldo recibe volúmenes cifrados con LUKS.
- **Almacén de configuración de conocimiento cero**: Sincronización opcional de configuración cifrada entre dispositivos. Las configuraciones se cifran del lado del cliente con AES-256-GCM antes de subirse. El servidor solo almacena blobs opacos. El servidor no puede leer claves SSH, credenciales, direcciones IP ni datos de configuración en texto plano. La derivación de claves usa passkey PRF extension + HKDF con separación de dominio. El acceso de miembros se gestiona mediante intercambio de claves X25519, y la revocación es inmediata.

Para detalles sobre estas capacidades, consulta [Arquitectura](/es/docs/architecture), [Repositorios](/es/docs/repositories), [Almacenamiento de configuración](/es/docs/config-storage) y [Seguridad de cuenta](/es/docs/account-security).

## Por qué importa

Las fallas de cumplimiento son costosas. Muy costosas. Los casos a continuación muestran problemas que la arquitectura de Rediacc previene estructuralmente:

| Incidente | Multa | Qué salió mal |
|-----------|-------|---------------|
| [Meta: transferencias de datos UE-EE.UU.](https://www.dataprotection.ie/en/news-media/press-releases/Data-Protection-Commission-announces-conclusion-of-inquiry-into-Meta-Ireland) | 1.200 M EUR | Datos personales transferidos a través de fronteras sin salvaguardas adecuadas. Autoalojado significa sin transferencia. |
| [Equifax: datos sin cifrar](https://www.ftc.gov/news-events/news/press-releases/2019/07/equifax-pay-575-million-part-settlement-ftc-cfpb-states-related-2017-data-breach) | 700 M USD | 147 millones de registros almacenados sin cifrar con pobre segmentación de red. LUKS2 es obligatorio, no opcional. |
| [Target: movimiento lateral](https://oag.ca.gov/news/press-releases/attorney-general-becerra-target-settles-record-185-million-credit-card-data) | 18,5 M USD | Los atacantes pivotaron de un proveedor de HVAC a sistemas de pago a través de una red plana. El aislamiento por repositorio lo previene. |
| [Anthem: PHI sin cifrar](https://www.hhs.gov/hipaa/for-professionals/compliance-enforcement/agreements/anthem/index.html) | 16 M USD | 79 millones de registros de salud almacenados sin cifrar. LUKS2 AES-256 está siempre activo. |
| [Blackbaud: cascada de brecha SaaS](https://www.sec.gov/newsroom/press-releases/2023-48) | 49,5 M USD | El ransomware en un proveedor SaaS expuso datos de más de 13.000 organizaciones clientes. Autoalojado significa que una brecha del proveedor no puede alcanzar tus datos. |
| [British Airways: pobre segmentación](https://www.edpb.europa.eu/news/national-news/2019/ico-statement-intention-fine-british-airways-ps18339m-under-gdpr-data_en) | 20 M GBP | Los atacantes inyectaron código malicioso debido a controles de red inadecuados. Docker daemons aislados e iptables previenen el acceso lateral. |
| [Google: derecho al olvido](https://www.edpb.europa.eu/news/national-news/2019/cnils-restricted-committee-imposes-financial-penalty-50-million-euros_en) | 50 M EUR | Dificultad para borrar completamente datos en sistemas distribuidos. La eliminación criptográfica vía destrucción de LUKS es instantánea y completa. |

## Aviso importante

Estas páginas explican cómo la arquitectura de Rediacc se alinea con los requisitos de cumplimiento. Pero aquí está la realidad: el cumplimiento es más grande que el software. Necesitarás políticas, procedimientos, capacitación y probablemente auditorías de terceros. Rediacc maneja la parte de infraestructura. Trabaja con tus equipos legal y de cumplimiento en el resto.
