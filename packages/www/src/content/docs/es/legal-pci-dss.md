---
title: "Cumplimiento de PCI DSS"
description: "Cómo Rediacc cumple con los requisitos de PCI DSS: copias de seguridad inmutables, aislamiento automático de red y control de acceso a nivel de infraestructura."
category: "Legal"
order: 6
language: es
sourceHash: "d8391036876231a0"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

Mira, PCI DSS v4.0.1. no es opcional si manejas datos de titular de tarjeta. La versión 4.0.1. se reduce a un requisito: aislamiento a nivel de infraestructura de todo lo demás.

Referencia: [PCI Security Standards Council](https://www.pcisecuritystandards.org/document_library/)

## Mapeo de requisitos

| Requisito PCI DSS | Descripción | Capacidad de Rediacc |
|-------------------|-------------|---------------------|
| **Req 1**, Controles de seguridad de red | Instalar y mantener controles de seguridad de red | Reglas iptables por repositorio bloquean todo tráfico entre repositorios. Cada repositorio obtiene su propia subred de IP loopback (/26). |
| **Req 2**, Configuraciones seguras | Aplicar configuraciones seguras a todos los componentes del sistema | Los hooks del ciclo de vida de Rediaccfile imponen configuraciones determinísticas y reproducibles. Sin credenciales predeterminadas. Las claves LUKS las genera el operador. |
| **Req 3**, Proteger datos almacenados | Proteger datos de cuenta almacenados con cifrado | Cifrado LUKS2 AES-256 en todos los volúmenes de repositorios. El cifrado es obligatorio, no opcional. Eliminación criptográfica vía destrucción de clave LUKS. |
| **Req 4**, Proteger datos en tránsito | Proteger datos del titular con criptografía fuerte durante la transmisión | Todas las operaciones remotas por SSH. Transporte de respaldo cifrado de extremo a extremo. Sin rutas de datos sin cifrar. |
| **Req 6**, Desarrollo seguro | Desarrollar y mantener sistemas y software seguros | La clonación CoW crea entornos de prueba aislados sin exponer datos de tarjetas de producción a redes de desarrollo. Flujo de trabajo fork-test-promote. |
| **Req 7**, Restringir acceso | Restringir acceso a componentes del sistema y datos del titular por necesidad de negocio | Sockets de Docker daemon por repositorio. El acceso a un repositorio no otorga acceso a otro. Autenticación basada en clave SSH. |
| **Req 8**, Identificar usuarios y autenticar | Identificar usuarios y autenticar acceso a componentes del sistema | Autenticación por clave SSH. Tokens API con vinculación IP y permisos de alcance definido. Autenticación de dos factores (TOTP). |
| **Req 9**, Restringir acceso físico | Restringir acceso físico a datos del titular de tarjetas | Autoalojado: la seguridad física está bajo tu control directo. El cifrado LUKS hace ilegibles los discos robados. |
| **Req 10**, Registrar y monitorear | Registrar y monitorear todo acceso a componentes del sistema y datos del titular | Más de 70 tipos de eventos (autenticación, tokens API, configuración, licencias, operaciones de máquina). Panel de administración y portal con filtrado por usuario, equipo, tipo y fecha. CLI `rdc audit` para exportación programática. Operaciones de máquina también en registros del sistema para defensa en profundidad. |
| **Req 12**, Políticas organizacionales | Apoyar la seguridad de la información con políticas y programas organizacionales | El autoalojamiento elimina el alcance del procesador tercero (Req 12.8). Reduce el perímetro de cumplimiento PCI DSS. |

## Segmentación de red

PCI DSS enfatiza mucho la segmentación. Veo constantemente que los equipos superponen reglas iptables sobre aislamiento insuficiente. Eso no funciona. Los equipos que pasan tienen segmentación integrada en la arquitectura. Rediacc te da eso por defecto:

- Cada repositorio se ejecuta en su propio Docker daemon en `/var/run/rediacc/docker-<networkId>.sock`
- Los repositorios tienen subredes de IP loopback aisladas (127.0.x.x/26, 61 IPs utilizables por red)
- Las reglas iptables aplicadas por renet bloquean todo tráfico entre daemons
- Los contenedores de diferentes repositorios no pueden comunicarse a nivel de red

Un repositorio de procesamiento de pagos se ejecuta en su propio Docker daemon y su propia subred loopback, aislado de red de todas las demás aplicaciones en la misma máquina. No hay reglas de firewall adicionales que escribir.

## Reducción de alcance

Rediacc autoalojado reduce el alcance de cumplimiento. No necesitas configurar manualmente la segmentación de red; es automática por diseño. Nuestra documentación para esta parte aún necesita trabajo, pero el aislamiento es sólido.

- Sin proveedor de nube tercero en el flujo de datos del titular
- Sin proveedor SaaS que evaluar bajo Req 12.8 (proveedores de servicio terceros)
- Controles de seguridad física bajo tu gestión directa
- Claves de cifrado almacenadas solo en la configuración local del operador

## Casos de aplicación

La mayoría de los fallos de auditoría PCI se reducen a una de dos cosas: segmentación que nunca fue aislada adecuadamente, o cifrado que nunca fue probado contra ataques reales.

- Heartland Payment Systems (2008): los atacantes se movieron lateralmente a través de 48 bases de datos debido a la pobre segmentación de red, exponiendo 130 millones de números de tarjetas. [El costo total superó los 200 millones de dólares.](https://www.philadelphiafed.org/-/media/frbp/assets/consumer-finance/discussion-papers/d-2010-january-heartland-payment-systems.pdf)
- Target (2013): los atacantes pivotaron del acceso de red de un proveedor HVAC a sistemas de punto de venta debido a la arquitectura de red plana, capturando 40 millones de tarjetas de pago. [Acuerdo por 18,5 millones de dólares con 47 fiscales generales estatales.](https://oag.ca.gov/news/press-releases/attorney-general-becerra-target-settles-record-185-million-credit-card-data)
