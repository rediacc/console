---
title: "Cumplimiento del GDPR"
description: "Cómo la arquitectura autoalojada de Rediacc se ajusta a los requisitos del GDPR para la protección de datos y privacidad."
category: "Legal"
order: 1
language: es
sourceHash: "e3d383739190bb30"
---

El Reglamento General de Protección de Datos (GDPR) es la ley de protección de datos de la Unión Europea, vigente desde mayo de 2018. Regula cómo las organizaciones recopilan, procesan y almacenan datos personales de personas en la UE.

Texto completo: [Reglamento (UE) 2016/679](https://gdpr-info.eu/)

## Mapeo de artículos

La tabla a continuación mapea artículos específicos del GDPR a las capacidades técnicas de Rediacc.

| Artículo | Requisito | Capacidad de Rediacc |
|----------|-----------|---------------------|
| [Art. 5](https://gdpr-info.eu/art-5-gdpr/), Principios | Minimización de datos, integridad, confidencialidad | Los clones CoW (`cp --reflink=always`) duplican datos en la misma máquina sin transferencia de red. LUKS2 AES-256 cifra todos los datos en reposo. |
| [Art. 17](https://gdpr-info.eu/art-17-gdpr/), Derecho al olvido | Eliminar datos personales a solicitud | `rdc repo destroy` elimina criptográficamente el volumen LUKS. Eliminar un fork remueve la copia clonada completamente. |
| [Art. 25](https://gdpr-info.eu/art-25-gdpr/), Protección de datos por diseño | Privacidad por defecto | El cifrado es obligatorio, no opcional. Cada repositorio obtiene un Docker daemon aislado y una red propia. Sin compartición de datos entre repositorios. El almacén de configuración usa cifrado de conocimiento cero: las configuraciones se cifran del lado del cliente con AES-256-GCM antes de subirse, por lo que el servidor no puede leer datos en texto plano. |
| [Art. 28](https://gdpr-info.eu/art-28-gdpr/), Procesador | Obligaciones de procesamiento de datos de terceros | Autoalojado: Rediacc se ejecuta en tu infraestructura. Ningún dato sale de tu máquina durante operaciones de fork, clonación o respaldo. Ningún componente SaaS procesa datos personales. |
| [Art. 30](https://gdpr-info.eu/art-30-gdpr/), Registros de procesamiento | Mantener registros de actividades de procesamiento | El registro de auditoría rastrea más de 40 tipos de eventos a nivel de cuenta: autenticación, tokens API, operaciones del almacén de configuración y licencias. Exportación vía `rdc audit` CLI o panel de administración. |
| [Art. 32](https://gdpr-info.eu/art-32-gdpr/), Seguridad del procesamiento | Medidas técnicas apropiadas | Cifrado LUKS2 AES-256 en reposo, aislamiento de red vía iptables y Docker daemons separados, subredes de IP loopback (/26) por repositorio. El almacén de configuración usa cifrado de triple capa: claves SDK con ventana temporal, derivación de CEK con clave dividida (passkey + secreto del servidor) y cifrado con frase de paso de la organización. |
| [Art. 33](https://gdpr-info.eu/art-33-gdpr/), Notificación de brechas | Notificación en 72 horas con rastro forense | Los registros de auditoría proporcionan un rastro forense de todas las operaciones. La arquitectura autoalojada limita el radio de impacto a repositorios individuales. |

## Residencia de datos

Los clones CoW nunca abandonan la máquina de origen. El comando `rdc repo fork` crea una copia a nivel de sistema de archivos usando reflinks. No se transfieren datos por la red.

Para operaciones entre máquinas, `rdc repo backup push/pull` transfiere datos por SSH. El destino de respaldo recibe volúmenes cifrados con LUKS que no pueden leerse sin las credenciales del operador.

## Clonación de entornos y enmascaramiento de datos

Al clonar entornos de producción para desarrollo o pruebas, el hook del ciclo de vida `up()` del Rediaccfile ejecuta scripts de sanitización después de crear un fork: eliminar PII de bases de datos, reemplazar correos reales con direcciones de prueba, remover tokens API y datos de sesión, anonimizar archivos de log. El entorno de desarrollo obtiene la estructura de producción sin las identidades de producción, satisfaciendo el principio de minimización de datos ([Art. 5(1)(c)](https://gdpr-info.eu/art-5-gdpr/)).

## Almacén de configuración de conocimiento cero

El almacén de configuración opcional permite sincronizar configuraciones del CLI entre dispositivos. Está diseñado para que el servidor tenga cero conocimiento del contenido de las configuraciones:

- **Cifrado del lado del cliente**: Las configuraciones se cifran con AES-256-GCM antes de subirse. La clave de cifrado (CEK) se deriva de un secreto passkey PRF y un secreto del servidor usando HKDF con separación de dominio. Ninguna de las partes puede derivar la clave por sí sola.
- **El servidor solo ve blobs opacos**: Claves SSH, credenciales, direcciones IP, topología de red. Nada de esto es visible para el servidor. Solo metadatos (IDs de configuración, versiones, marcas de tiempo) se almacenan en texto plano.
- **Acceso de miembros vía X25519**: Cuando se agrega un miembro del equipo, la CEK se cifra con su clave pública X25519 y se transmite a través del servidor. El servidor nunca ve la CEK en texto plano.
- **Revocación inmediata**: Eliminar un miembro borra su CEK envuelta y revoca sus tokens. Las configuraciones futuras usan nuevas épocas SDK inaccesibles para el miembro eliminado.
- **Tokens rotativos**: La autenticación del CLI usa tokens rotativos de un solo uso (ventana de gracia de 3 solicitudes), vinculados a IP en el primer uso, con expiración automática de 24 horas.

Incluso un compromiso total del servidor no puede exponer el contenido de las configuraciones. El servidor nunca tiene la clave.

Para más detalles, consulta [Almacenamiento de configuración](/es/docs/config-storage).

## Controlador y procesador de datos

Dado que Rediacc es software autoalojado, tu organización es tanto el controlador como el procesador de datos. Rediacc (la empresa) no accede, procesa ni almacena tus datos. No se requiere un acuerdo de procesamiento de datos con Rediacc para el producto autoalojado, ya que ningún dato personal fluye hacia la infraestructura de Rediacc.

El almacén de configuración es el único componente que toca los servidores de Rediacc (para sincronización), pero su diseño de conocimiento cero significa que el servidor solo almacena blobs cifrados que no puede descifrar.
