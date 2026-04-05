---
title: "Cumplimiento de CCPA"
description: "Cómo el modelo autoalojado de Rediacc cumple con los requisitos de la Ley de Privacidad del Consumidor de California para la protección de datos del consumidor."
category: "Legal"
order: 4
language: es
sourceHash: "50081a040deb3183"
---

La Ley de Privacidad del Consumidor de California (CCPA) es una ley estatal que otorga a los consumidores de California derechos sobre su información personal, incluyendo el derecho a saber qué datos se recopilan, el derecho a eliminarlos y el derecho a optar por no participar en su venta.

Referencia: [Fiscal General de California, CCPA](https://oag.ca.gov/privacy/ccpa)

## Mapeo de derechos del consumidor

CCPA se centra en los derechos del consumidor relacionados con la información personal. Rediacc es una herramienta autoalojada desplegada en tu infraestructura, no un servicio de terceros que recopila o vende datos del consumidor. La tabla a continuación muestra cómo Rediacc apoya el cumplimiento de CCPA de tu organización.

| Derecho CCPA | Requisito | Capacidad de Rediacc |
|-------------|-----------|---------------------|
| Derecho a saber (1798.100) | Divulgar categorías y propósitos de los datos recopilados | Los registros de auditoría rastrean todas las operaciones de datos. Autoalojado: tu organización mantiene visibilidad completa sobre los datos existentes en cada repositorio. |
| Derecho a eliminar (1798.105) | Eliminar la información personal del consumidor a solicitud | `rdc repo destroy` elimina criptográficamente el volumen cifrado con LUKS. La eliminación de forks remueve las copias clonadas completamente. |
| Derecho a optar por no participar (1798.120) | No vender ni compartir información personal | Arquitectura autoalojada: no se transfieren datos a Rediacc ni a terceros. Los datos permanecen en tus servidores. La sincronización del almacén de configuración utiliza cifrado de conocimiento cero. Ni siquiera el servidor de sincronización puede leer los datos. |
| Seguridad de datos (1798.150) | Implementar medidas de seguridad razonables | Cifrado LUKS2 AES-256, aislamiento de red, acceso solo por SSH, Docker daemons aislados, registro de auditoría. El almacén de configuración utiliza cifrado de triple capa con derivación de clave dividida y tokens rotativos de un solo uso. |

## Estado como proveedor de servicios

Rediacc como software no accede, procesa ni almacena datos del consumidor. Tu equipo de TI opera Rediacc en tu propia infraestructura. No fluyen datos hacia la empresa Rediacc. Las implicaciones:

- Rediacc no es un "proveedor de servicios" bajo CCPA (no procesa datos en tu nombre)
- No se requiere un acuerdo de procesamiento de datos con Rediacc para el producto autoalojado
- Tus obligaciones bajo CCPA son entre tu organización y tus consumidores

## Inventario de datos

Cada repositorio de Rediacc es una unidad de datos discreta y cifrada con un GUID único. Puedes inventariar exactamente qué datos existen y dónde:

- `rdc machine query <machine> --repositories` lista todos los repositorios en una máquina con tamaño y estado de montaje
- Cada repositorio está aislado a nivel de sistema de archivos, red y contenedores
- Se rastrean las relaciones de fork, para que puedas identificar todas las copias de un conjunto de datos

CCPA requiere mapeo de datos. El modelo de repositorios de Rediacc lo proporciona: un GUID por conjunto de datos, enumerable por máquina, con linaje de forks rastreado.
