---
title: Aplicación Web
description: Comprensión de la arquitectura y el despliegue de aplicaciones web con Rediacc
category: Reference
order: 1
language: es
---

# Guía de Usuario de la Plataforma Rediacc

## Descripción General

**Rediacc** es una plataforma en la nube que ofrece servicios de respaldo impulsados por IA.

Esta guía explica el uso básico de la interfaz web en [https://www.rediacc.com/](https://www.rediacc.com/).

### Propósito de esta Guía

- Ayudar a los nuevos usuarios a adaptarse rápidamente a la plataforma
- Explicar funciones básicas (gestión de recursos, respaldo) paso a paso

---

## 1. Creación de Cuenta e Inicio de Sesión

### 1.1 Registro

![Registration process walkthrough](/assets/videos/user-guide/01-01-registration.webm)
*(Video: Complete registration flow from start to finish)*

Para comenzar a utilizar la plataforma Rediacc, primero necesita crear una cuenta.

![Página de inicio de sesión de Rediacc - infraestructura siempre activa](/assets/images/user-guide/01_login.png)
*(Figura 1: Página principal de inicio de sesión, mostrando las características principales de la plataforma Rediacc)*

1. Navegue a [https://www.rediacc.com/](https://www.rediacc.com/) en su navegador.
2. Haga clic en el botón **{{t:auth.login.signIn}}** en la esquina superior derecha de la página.
3. Elija **Comenzar** para acceso gratuito o **Solicitar demostración** para una demostración.

> **Consejo**: Puede crear una cuenta gratuita sin necesidad de tarjeta de crédito. Incluye 10 núcleos de CPU y equipos ilimitados.

![Formulario de inicio de sesión de Rediacc - campos de correo electrónico y contraseña](/assets/images/user-guide/02_register.png)
*(Figura 2: Pantalla de inicio de sesión para usuarios existentes)*

4. Si no tiene una cuenta, haga clic en el enlace **{{t:auth.login.register}}** para crear una nueva cuenta.

5. Complete la siguiente información en el formulario que se abre:
   - **{{t:auth.registration.organizationName}}**: Ingrese el nombre de su organización
   - **{{t:auth.login.email}}**: Ingrese una dirección de correo electrónico válida
   - **{{t:auth.login.password}}**: Cree una contraseña con al menos 8 caracteres
   - **{{t:auth.registration.passwordConfirm}}**: Vuelva a ingresar la misma contraseña

![Modal Crear Cuenta - pasos registrar, verificar y completar](/assets/images/user-guide/03_create_account.png)
*(Figura 3: Formulario de registro de nuevo usuario paso a paso - Registrar > Verificar > Completar)*

6. Marque la casilla para aceptar los términos de servicio y la política de privacidad.
7. Haga clic en el botón **{{t:auth.registration.createAccount}}**.

> **Consejo**: La contraseña debe tener al menos 8 caracteres y debe ser segura. Todos los campos son obligatorios.

8. Ingrese el código de verificación de 6 dígitos enviado a su correo electrónico en las casillas secuencialmente.
9. Haga clic en el botón **{{t:auth.registration.verifyAccount}}**.

![Entrada de código de verificación - código de activación de 6 dígitos](/assets/images/user-guide/04_verification_code.png)
*(Figura 4: Ventana para ingresar el código de activación enviado al administrador)*

> **Consejo**: El código de verificación es válido por un tiempo limitado. Si no recibe el código, revise su carpeta de spam.

---

### 1.2 Inicio de Sesión

![Sign in process walkthrough](/assets/videos/user-guide/01-02-login.webm)
*(Video: Complete sign in flow)*

Después de crear su cuenta, puede iniciar sesión en la plataforma.

1. Complete el campo **{{t:auth.login.email}}** (obligatorio si aparece una advertencia roja).
2. Complete el campo **{{t:auth.login.password}}**.
3. Haga clic en el botón **{{t:auth.login.signIn}}**.

![Formulario de inicio de sesión - campos obligatorios con advertencia de error](/assets/images/user-guide/05_sign_in.png)
*(Figura 5: Formulario de inicio de sesión - los mensajes de error están marcados con un borde rojo)*

> **Consejo**: Si el mensaje de error dice "Este campo es obligatorio", complete los campos vacíos. Contacte al administrador para contraseñas olvidadas.

4. Después de iniciar sesión correctamente, será redirigido a la pantalla **{{t:common.navigation.dashboard}}**.

![Panel de Rediacc - lista de máquinas y menú lateral](/assets/images/user-guide/06_dashboard.png)
*(Figura 6: Panel principal después de iniciar sesión correctamente - menús de Organización, Máquinas y Configuración en la barra lateral izquierda)*

> **Consejo**: El panel se actualiza automáticamente. Puede actualizar la página con F5 para obtener información actualizada.

---

## 2. Descripción General de la Interfaz

Después de iniciar sesión, la pantalla que ve consta de estas secciones principales:

- **{{t:common.navigation.organization}}**: Usuarios, equipos y control de acceso
- **{{t:common.navigation.machines}}**: Gestión de servidores y repositorios
- **{{t:common.navigation.settings}}**: Configuración de perfil y sistema
- **{{t:common.navigation.storage}}**: Gestión de área de almacenamiento
- **{{t:common.navigation.credentials}}**: Credenciales de acceso
- **{{t:common.navigation.queue}}**: Gestión de cola de trabajos
- **{{t:common.navigation.audit}}**: Registros de auditoría del sistema

---

## 2.1 Organización - Usuarios

La gestión de usuarios le permite controlar el acceso a la plataforma para las personas de su organización.

### 2.1.1 Agregar Usuarios

![Adding users walkthrough](/assets/videos/user-guide/02-01-01-user-create.webm)
*(Video: Creating a new user)*

1. Haga clic en **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationUsers}}** en la barra lateral izquierda.
2. Vea la lista de todos los usuarios en formato de tabla.
3. Cada fila de usuario muestra correo electrónico, estado ({{t:organization.users.status.active}}/{{t:organization.users.status.inactive}}), grupo de permisos y hora de última actividad.

![Página de gestión de usuarios - lista de usuarios activos](/assets/images/user-guide/07_users.png)
*(Figura 7: Sección de Usuarios en Organización - se muestra la información de todos los usuarios)*

4. Haga clic en el icono **"+"** en la esquina superior derecha.
5. Haga clic en el botón **{{t:organization.users.modals.createTitle}}** y complete el formulario que se abre:
   - **{{t:organization.users.form.emailLabel}}**: Ingrese la dirección de correo electrónico del usuario
   - **{{t:organization.users.form.passwordLabel}}**: Ingrese una contraseña temporal

![Modal de creación de usuario - campos de correo electrónico y contraseña](/assets/images/user-guide/08_user_add.png)
*(Figura 8: Ventana modal para agregar nuevo usuario - formulario de creación de usuario simple y rápido)*

6. Haga clic en el botón **{{t:common.actions.create}}**.

> **Consejo**: Las credenciales de inicio de sesión deben comunicarse de forma segura al usuario creado. Se recomienda cambiar la contraseña en el primer inicio de sesión.

![Lista de usuarios - vista de tabla completa con tres usuarios](/assets/images/user-guide/09_user_list.png)
*(Figura 9: Todos los usuarios activos e inactivos en la página de gestión de usuarios)*

> **Consejo**: La página muestra automáticamente 20 registros. Use la paginación para ver más registros.

### 2.1.2 Asignación de Permisos de Usuario

![User permissions walkthrough](/assets/videos/user-guide/02-01-02-user-permissions.webm)
*(Video: Assigning permission groups to users)*

Puede gestionar los derechos de acceso asignando grupos de permisos específicos a los usuarios.

1. Seleccione un usuario de la pestaña **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationUsers}}**.
2. Haga clic en el icono de escudo en la columna de acciones (**{{t:organization.access.tabs.permissions}}**).

![Gestión de permisos - iconos de escudo, engranaje y eliminar](/assets/images/user-guide/10_users_permissions.png)
*(Figura 10: Visualización de iconos de acciones de usuario - cada icono representa una acción diferente)*

3. Seleccione un **{{t:organization.users.modals.permissionGroupLabel}}** del formulario que se abre.
4. El número de usuarios y permisos en el grupo se muestra junto al usuario.
5. Haga clic en el botón **{{t:organization.users.modals.assignTitle}}** para guardar los cambios.

![Modal de asignación de permisos - grupo Administradores](/assets/images/user-guide/11_user_permissions_form.png)
*(Figura 11: Modal para asignar grupo de permisos al usuario seleccionado - menú desplegable con grupos disponibles)*

> **Consejo**: Algunos grupos de permisos son fijos por el sistema y no se pueden cambiar.

### 2.1.3 Activación de Usuario

![User activation walkthrough](/assets/videos/user-guide/02-01-03-user-activation.webm)
*(Video: Activating an inactive user)*

Puede reactivar usuarios deshabilitados.

1. Encuentre el usuario con estado inactivo en la lista de **Usuarios**.
2. Haga clic en el icono rojo en la columna de acciones.

![Activación de usuario - vista de tooltip "Activar"](/assets/images/user-guide/12_users_activation.png)
*(Figura 12: Activando un usuario inactivo)*

3. Haga clic en el botón **{{t:common.general.yes}}** en la ventana de confirmación.

![Modal de confirmación de activación](/assets/images/user-guide/13_users_activation_confirm.png)
*(Figura 13: Ventana modal para confirmar la activación del usuario)*

> **Consejo**: Esta acción es reversible. Puede desactivar el usuario de la misma manera.

### 2.1.4 Rastreo de Usuario

![User trace walkthrough](/assets/videos/user-guide/02-01-04-user-trace.webm)
*(Video: Viewing user activity trace)*

Puede usar la función de rastreo para monitorear las actividades de los usuarios.

1. Seleccione un usuario y haga clic en el icono de engranaje en la columna de acciones.
2. Haga clic en la opción **{{t:common.actions.trace}}** para abrir el historial de actividad del usuario.

![Rastreo de usuario - tooltip "Trace" con botón de acción](/assets/images/user-guide/14_users_trace.png)
*(Figura 14: Opción de rastreo de actividad del usuario)*

3. Las actividades pasadas del usuario se listan en la pantalla abierta.
4. Las estadísticas se muestran en la parte superior: Total de Registros, Registros Vistos, Última Actividad.
5. Haga clic en el botón **{{t:common.actions.export}}** y seleccione el formato: **{{t:common.exportCSV}}** o **{{t:common.exportJSON}}**.

![Historial de Auditoría - Opciones de exportación](/assets/images/user-guide/15_user_trace_export.png)
*(Figura 15: Historial de actividad completo del usuario - estadísticas, detalles y opciones de Exportar)*

> **Consejo**: Exporte regularmente los datos de auditoría para mantener registros de seguridad y cumplimiento. El formato CSV se puede abrir en Excel.

---

## 2.2 Organización - Equipos

Los equipos le permiten agrupar usuarios y proporcionar acceso masivo a los recursos.

### 2.2.1 Crear Equipos

![Creating teams walkthrough](/assets/videos/user-guide/02-02-01-team-create.webm)
*(Video: Creating a new team)*

1. Vaya a la pestaña **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationTeams}}**.
2. Haga clic en el botón **"+"**.
3. Ingrese el nombre de su equipo en el campo **{{t:common.vaultEditor.fields.TEAM.name.label}}**.
4. Complete los campos **{{t:common.vaultEditor.fields.TEAM.SSH_PRIVATE_KEY.label}}** y **{{t:common.vaultEditor.fields.TEAM.SSH_PUBLIC_KEY.label}}** en la sección **{{t:common.vaultEditor.vaultConfiguration}}**.

![Formulario de creación de nuevo equipo - nombre del equipo y claves SSH](/assets/images/user-guide/16_teams_create.png)
*(Figura 16: Creando un nuevo equipo dentro de "Private Team")*

5. Haga clic en el botón **{{t:common.actions.create}}** para guardar el equipo.

> **Consejo**: Las claves SSH son necesarias para la autenticación SSH de Bridge. Si recibe una advertencia de clave faltante, proporcione ambas claves.

### 2.2.2 Edición de Equipo

![Team editing walkthrough](/assets/videos/user-guide/02-02-02-team-edit.webm)
*(Video: Editing team information)*

1. Haga clic en el icono de lápiz junto al equipo que desea editar en la lista de equipos.
2. Cambie el nombre del equipo en el campo **{{t:common.vaultEditor.fields.TEAM.name.label}}** si es necesario.
3. Actualice las claves SSH en la sección **{{t:common.vaultEditor.vaultConfiguration}}**.
4. Haga clic en el botón **{{t:common.save}}** para aplicar los cambios.

![Formulario de edición de equipo - mensaje informativo azul](/assets/images/user-guide/17_teams_edit_form.png)
*(Figura 17: Editando la información de un equipo existente)*

> **Consejo**: La configuración del equipo se utiliza para la estructura organizativa. Los cambios surten efecto para todos los miembros del equipo.

### 2.2.3 Gestión de Miembros del Equipo

![Team members management walkthrough](/assets/videos/user-guide/02-02-03-team-members.webm)
*(Video: Managing team members)*

1. Seleccione un equipo y haga clic en el icono de usuario.
2. Vea los miembros ya asignados al equipo en la pestaña **{{t:organization.teams.manageMembers.currentTab}}**.
3. Cambie a la pestaña **{{t:organization.teams.manageMembers.addTab}}**.
4. Ingrese una dirección de correo electrónico o seleccione un usuario del menú desplegable.
5. Haga clic en el botón **"+"** para agregar el miembro al equipo.

![Formulario de gestión de miembros del equipo - pestañas "Miembros Actuales" y "Agregar Miembro"](/assets/images/user-guide/18_teams_members_form.png)
*(Figura 18: Panel de gestión de miembros del equipo)*

> **Consejo**: Puede asignar el mismo miembro a múltiples equipos.

### 2.2.4 Rastreo de Equipo

![Team trace walkthrough](/assets/videos/user-guide/02-02-04-team-trace.webm)
*(Video: Viewing team audit history)*

1. Seleccione el equipo que desea rastrear.
2. Haga clic en el icono de reloj/historial.
3. Revise los conteos de Registros Totales, Registros Vistos y Última Actividad en la ventana **{{t:resources.audit.title}}**.
4. Haga clic en el botón **{{t:common.actions.export}}** para exportar en formato {{t:common.exportCSV}} o {{t:common.exportJSON}}.

![Modal de historial de auditoría - equipo DataBassTeam](/assets/images/user-guide/19_teams_trace.png)
*(Figura 19: Visualización del historial de auditoría del equipo)*

> **Consejo**: El historial de auditoría es importante para el cumplimiento y el control de seguridad.

### 2.2.5 Eliminación de Equipo

![Team deletion walkthrough](/assets/videos/user-guide/02-02-05-team-delete.webm)
*(Video: Deleting a team)*

1. Haga clic en el icono de papelera (rojo) junto al equipo que desea eliminar.
2. Verifique que el nombre del equipo sea correcto en el cuadro de diálogo de confirmación.
3. Haga clic en el botón **{{t:common.general.yes}}**.

![Cuadro de diálogo de confirmación de eliminación de equipo](/assets/images/user-guide/20_teams_delete.png)
*(Figura 20: Confirmación de eliminación de equipo)*

> **Advertencia**: La eliminación del equipo es irreversible. Verifique si hay datos importantes en el equipo antes de eliminarlo.

---

## 2.3 Organización - Control de Acceso

El control de acceso le permite gestionar centralmente los permisos de usuario creando grupos de permisos.

### 2.3.1 Crear Grupos de Permisos

![Permission group creation walkthrough](/assets/videos/user-guide/02-03-01-permission-create.webm)
*(Video: Creating a permission group)*

1. Vaya a la pestaña **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationAccess}}**.
2. Haga clic en el botón **"+"**.
3. Introduzca un nombre significativo en el campo **{{t:organization.access.modals.groupPlaceholder}}**.
4. Haga clic en el botón **{{t:common.actions.confirm}}** para crear el grupo.

![Formulario de creación de grupo de permisos](/assets/images/user-guide/21_create_access.png)
*(Figura 21: Creando un nuevo Grupo de Permisos)*

> **Consejo**: Los grupos de permisos se utilizan para organizar usuarios con permisos similares. Mantenga nombres de grupo descriptivos (por ejemplo, "Admin", "Read Only", "Repository Manager").

### 2.3.2 Gestión de Permisos

![Permission management walkthrough](/assets/videos/user-guide/02-03-02-permission-manage.webm)
*(Video: Managing permissions for a group)*

1. Seleccione un Grupo de Permisos y haga clic en la opción **{{t:organization.access.modals.managePermissionsTitle}}**.
2. Vea los derechos de acceso del grupo en la pestaña **{{t:organization.access.modals.currentPermissionsTab}}**.
3. Puede revocar un permiso haciendo clic en el botón rojo **{{t:common.delete}}** junto a cada acción.
4. Haga clic en la pestaña **{{t:organization.access.modals.addPermissionsTab}}** para agregar nuevos permisos al grupo.

![Panel de gestión de permisos - lista de permisos asignados](/assets/images/user-guide/22_access_permission.png)
*(Figura 22: Gestionando Permisos para Grupo de Permisos)*

> **Consejo**: Otorgue permisos basados en el principio de privilegio mínimo. Revise regularmente y elimine permisos innecesarios.

---

## 2.4 Máquinas

La sección de Máquinas le permite gestionar sus servidores y recursos de repositorio.

### 2.4.1 Agregar Máquinas

![Adding machines walkthrough](/assets/videos/user-guide/02-04-01-machine-create.webm)
*(Video: Adding a new machine)*

1. Vaya a la pestaña **{{t:common.navigation.machines}}** desde el menú izquierdo.
2. Haga clic en el botón **{{t:machines.createMachine}}** en la esquina superior derecha.

![Página de máquinas - botón "Add Machine"](/assets/images/user-guide/23_machines_add.png)
*(Figura 23: Página principal de gestión de máquinas)*

3. Complete el formulario que se abre:
   - **{{t:machines.machineName}}**: Ingrese un nombre único (por ejemplo, "server-01")
   - **{{t:common.vaultEditor.fields.MACHINE.ip.label}}**: Ingrese la dirección IP de la máquina (por ejemplo, 192.168.111.11)
   - **{{t:common.vaultEditor.fields.MACHINE.datastore.label}}**: Especifique el directorio de almacenamiento (por ejemplo, /mnt/rediacc)
   - **{{t:common.vaultEditor.fields.MACHINE.user.label}}**: Ingrese el nombre de usuario SSH
   - **{{t:common.vaultEditor.fields.MACHINE.port.label}}**: Ingrese el número de puerto (predeterminado: 22)
   - **{{t:common.vaultEditor.fields.MACHINE.ssh_password.label}}**: Ingrese la contraseña (opcional)

![Formulario de adición de máquina - todos los campos](/assets/images/user-guide/24_machine_create.png)
*(Figura 24: Formulario de adición de nueva máquina - nombre de máquina, configuración de red, credenciales SSH)*

4. Haga clic en el botón **{{t:common.vaultEditor.testConnection.button}}** para verificar la conexión.
5. Después de que la prueba sea exitosa, haga clic en el botón **{{t:common.actions.create}}**.

> **Consejo**: Si la opción "Automatically start setup after machine creation" está marcada, la máquina realizará automáticamente pasos de configuración adicionales.

![Creación de máquina completada - ventana de seguimiento de tarea](/assets/images/user-guide/25_machine_create_complete.png)
*(Figura 25: Ventana de seguimiento de tarea después de que la máquina se crea correctamente)*

6. Observe las etapas: **{{t:queue.trace.assigned}}** → **Tratamiento** → **{{t:queue.statusCompleted}}**
7. Haga clic en el botón **{{t:common.actions.close}}** para cerrar la operación.

> **Consejo**: Haga clic en el botón "{{t:common.actions.refresh}}" para verificar manualmente el estado más reciente.

### 2.4.2 Prueba de Conectividad

![Connectivity test walkthrough](/assets/videos/user-guide/02-04-02-connectivity-test.webm)
*(Video: Running a connectivity test)*

Puede verificar el estado de conexión de las máquinas existentes.

1. Haga clic en el botón **{{t:machines.connectivityTest}}**.

![Botón de prueba de conectividad](/assets/images/user-guide/26_connectivity_test_button.png)
*(Figura 26: Botón de Prueba de Conectividad en la barra de herramientas de acciones de máquina)*

2. Vea la lista de máquinas a probar.
3. Haga clic en el botón **{{t:machines.runTest}}**.
4. Los resultados exitosos se muestran en verde, las fallas en rojo.

![Formulario de prueba de conectividad - lista de máquinas](/assets/images/user-guide/27_connectivity_test_form.png)
*(Figura 27: Formulario de prueba de conectividad - función de ping para máquinas seleccionadas)*

> **Consejo**: Si la prueba falla, verifique la dirección IP de la máquina y la configuración SSH.

### 2.4.3 Actualizar Lista de Máquinas

![Machine list refresh walkthrough](/assets/videos/user-guide/02-04-03-machine-refresh.webm)
*(Video: Refreshing the machine list)*

Haga clic en el botón **{{t:common.actions.refresh}}** para actualizar la lista de máquinas.

![Botón de actualizar](/assets/images/user-guide/28_refresh.png)
*(Figura 28: Botón de actualizar en la barra de herramientas de acciones de máquina)*

### 2.4.4 Detalles de Máquina

![Machine details walkthrough](/assets/videos/user-guide/02-04-04-machine-details.webm)
*(Video: Viewing machine details)*

1. Seleccione la máquina cuyos detalles desea ver.
2. Haga clic en el botón de icono de ojo (**{{t:common.viewDetails}}**).

![Botón Ver Detalles](/assets/images/user-guide/29_view_details_button.png)
*(Figura 29: Icono de ojo en la columna de acciones de máquina)*

3. El panel de detalles de la máquina se abre en el lado derecho:
   - **Nombre del host**: Nombre de la máquina
   - **Tiempo de actividad**: Tiempo de ejecución
   - **{{t:queue.trace.operatingSystem}}**: SO y versión
   - **{{t:queue.trace.kernelVersion}}**: Versión del kernel
   - **CPU**: Información del procesador
   - **Hora del sistema**: Reloj del sistema

![Panel de detalles de máquina - información del sistema](/assets/images/user-guide/30_machine_view_details.png)
*(Figura 30: Panel de detalles de máquina - hostname, uptime, SO, kernel, información de CPU)*

> **Consejo**: Revise regularmente esta información para verificar la compatibilidad del SO y la disponibilidad de recursos.

### 2.4.5 Edición de Máquina

![Machine editing walkthrough](/assets/videos/user-guide/02-04-05-machine-edit.webm)
*(Video: Editing machine settings)*

1. Seleccione la máquina que desea editar.
2. Haga clic en el botón de icono de lápiz (**{{t:common.actions.edit}}**).

![Botón de editar](/assets/images/user-guide/31_edit_button.png)
*(Figura 31: Icono de lápiz en la columna de acciones de máquina)*

3. Realice los cambios necesarios.
4. Haga clic en el botón **{{t:common.vaultEditor.testConnection.button}}**.
5. Cuando la conexión sea exitosa, haga clic en el botón **{{t:common.save}}**.

![Formulario de edición de máquina](/assets/images/user-guide/32_edit_form.png)
*(Figura 32: Formulario de edición de máquina - nombre de máquina, región y configuración de vault)*

> **Consejo**: Siempre ejecute "Probar conexión" después de cambiar la configuración crítica.

### 2.4.6 Rastreo de Máquina

![Machine trace walkthrough](/assets/videos/user-guide/02-04-06-machine-trace.webm)
*(Video: Viewing machine audit history)*

1. Seleccione la máquina y haga clic en el botón de icono de reloj (**{{t:common.actions.trace}}**).

![Botón de rastreo](/assets/images/user-guide/33_trace_button.png)
*(Figura 33: Icono de reloj en la columna de acciones de máquina)*

2. Revise las operaciones en la ventana de historial de auditoría:
   - **{{t:resources.audit.action}}**: Tipo de operación realizada
   - **Detalles**: Campos modificados
   - **{{t:resources.audit.performedBy}}**: Usuario que realizó la acción
   - **Marca de tiempo**: Fecha y hora

![Ventana de historial de auditoría de máquina](/assets/images/user-guide/34_trace_list.png)
*(Figura 34: Historial de auditoría - lista de todos los cambios)*

> **Consejo**: Haga clic en la columna Timestamp para ver los cambios en orden cronológico.

### 2.4.7 Eliminación de Máquina

![Machine deletion walkthrough](/assets/videos/user-guide/02-04-07-machine-delete.webm)
*(Video: Deleting a machine)*

1. Seleccione la máquina que desea eliminar.
2. Haga clic en el botón de icono de papelera (**{{t:common.delete}}**).

![Botón de eliminar](/assets/images/user-guide/35_delete_button.png)
*(Figura 35: Icono de papelera en la columna de acciones de máquina)*

3. Haga clic en el botón **{{t:common.delete}}** en la ventana de confirmación.

![Ventana de confirmación de eliminación de máquina](/assets/images/user-guide/36_delete_form.png)
*(Figura 36: Ventana de confirmación "¿Está seguro de que desea eliminar esta máquina?")*

> **Advertencia**: Cuando se elimina una máquina, todas las definiciones de repositorio en ella también se eliminan. Esta acción es irreversible.

### 2.4.8 Operaciones Remotas

![Remote operations walkthrough](/assets/videos/user-guide/02-04-08-remote-hello.webm)
*(Video: Running remote operations on a machine)*

Puede realizar varias operaciones remotas en las máquinas.

1. Seleccione la máquina y haga clic en el botón **{{t:common.actions.remote}}**.
2. Vea las opciones en el menú desplegable:
   - **{{t:machines.runAction}}**: Ejecutar función en la máquina
   - **{{t:common.vaultEditor.testConnection.button}}**: Hacer ping a la máquina

![Menú remoto - Ejecutar en el servidor y Probar conexión](/assets/images/user-guide/37_remote_button.png)
*(Figura 37: Botón Remote - menú de ejecución de funciones en la máquina seleccionada)*

> **Consejo**: Use la opción "{{t:common.vaultEditor.testConnection.button}}" para verificar que la máquina sea accesible antes de ejecutar funciones.

#### Configuración

1. Seleccione la opción **{{t:machines.runAction}}**.
2. Encuentre la función **Configuración** en la lista **{{t:functions.availableFunctions}}**.
3. Haga clic en el nombre de la función para seleccionarla.

![Lista de funciones de máquina - función setup](/assets/images/user-guide/38_server_setup.png)
*(Figura 38: Función Configuración - prepara la máquina con herramientas y configuraciones requeridas)*

> **Consejo**: Se recomienda ejecutar la función "setup" primero al configurar una nueva máquina.

#### Verificación de Conexión (Hola)

1. Seleccione **{{t:machines.runAction}}** > función **Hola**.
2. Haga clic en el botón **{{t:common.actions.addToQueue}}**.

![Selección de función hello](/assets/images/user-guide/39_remote_hello.png)
*(Figura 39: Función Hola - función de prueba simple, devuelve el nombre del host)*

3. Observe los resultados en la ventana de seguimiento de tarea.
4. Vea la salida de la máquina en la sección **{{t:queue.trace.responseConsole}}**.

![Función hello completada](/assets/images/user-guide/40_remote_hello_complete.png)
*(Figura 40: Función Hola completada exitosamente - respuesta del nombre del host)*

> **Consejo**: La función hello es ideal para verificar la conectividad de la máquina.

#### Operaciones Avanzadas

1. Siga la ruta **{{t:common.actions.remote}}** > **{{t:machines.runAction}}** > **{{t:common.actions.advanced}}**.
2. Vea las funciones disponibles: setup, hello, ping, ssh_test, uninstall
3. Seleccione la función requerida y haga clic en el botón **{{t:common.actions.addToQueue}}**.

![Lista de funciones avanzadas](/assets/images/user-guide/41_remote_advanced.png)
*(Figura 41: Opción Avanzada - lista de funciones avanzadas)*

> **Consejo**: Asegúrese de que la configuración de la máquina esté completa antes de usar funciones avanzadas.

#### Prueba Rápida de Conectividad

![Menú remoto - Probar conexión](/assets/images/user-guide/42_connectivity_test.png)
*(Figura 42: Opción Probar conexión del menú Remote)*

> **Consejo**: Si la máquina tiene problemas de SSH o de red, puede identificar rápidamente los problemas con esta prueba.

---

## 2.5 Creación y Operaciones de Repositorio

Los repositorios son las unidades fundamentales donde se almacenan sus datos de respaldo.

### 2.5.1 Crear Repositorios

![Repository creation walkthrough](/assets/videos/user-guide/02-05-01-repository-create.webm)
*(Video: Creating a new repository)*

1. Seleccione una máquina de la pestaña **{{t:common.navigation.machines}}**.
2. Haga clic en el botón **{{t:machines.createRepository}}** en la esquina superior derecha.

![Botón Crear Repositorio](/assets/images/user-guide/43_create_repo_add.png)
*(Figura 43: Pantalla de gestión de repositorio de máquina - botón Crear Repositorio)*

3. Complete el formulario:
   - **{{t:common.vaultEditor.fields.REPOSITORY.name.label}}**: Introduzca el nombre del repositorio (por ejemplo, postgresql)
   - **{{t:resources.repositories.size}}**: Introduzca el tamaño del repositorio (por ejemplo, 2GB)
   - **{{t:resources.repositories.repositoryGuid}}**: Vea la credencial generada automáticamente
   - **{{t:resources.templates.selectTemplate}}**: Elija una plantilla (por ejemplo, databases_postgresql)

![Formulario de creación de repositorio](/assets/images/user-guide/44_repo_form.png)
*(Figura 44: Formulario de creación de repositorio - nombre del repositorio, tamaño y selección de plantilla)*

4. Haga clic en el botón **{{t:common.actions.create}}**.

> **Consejo**: El Credential ID se genera automáticamente, no se recomienda la modificación manual.

5. Observe las etapas en la ventana de seguimiento de tarea: **{{t:queue.trace.assigned}}** → **Tratamiento** → **{{t:queue.statusCompleted}}**

![Creación de repositorio completada](/assets/images/user-guide/45_repo_complete.png)
*(Figura 45: Creación de repositorio en cola - monitoreo de tarea)*

6. Haga clic en el botón **{{t:common.actions.close}}**.

> **Consejo**: La tarea típicamente se completa en 1-2 minutos.

![Lista de repositorios](/assets/images/user-guide/46_repo_list.png)
*(Figura 46: El repositorio creado aparece en la lista)*

### 2.5.2 Fork de Repositorio

![Repository fork walkthrough](/assets/videos/user-guide/02-05-02-repository-fork.webm)
*(Video: Forking a repository)*

Puede crear un nuevo repositorio copiando uno existente.

1. Seleccione el repositorio que desea copiar.
2. Haga clic en el menú **fx** (función).
3. Haga clic en la opción **fork**.

![Menú fx - opción fork](/assets/images/user-guide/47_fork_button.png)
*(Figura 47: Menú fx en el lado derecho - operaciones de repositorio)*

4. Introduzca una nueva etiqueta en el campo **{{t:functions.functions.fork.params.tag.label}}** (por ejemplo, 2025-12-06-20-37-08).
5. Haga clic en el botón **{{t:common.actions.addToQueue}}**.

![Formulario de configuración de fork](/assets/images/user-guide/48_fork_form.png)
*(Figura 48: Especifique la nueva etiqueta para el repositorio en la operación fork)*

6. Espere el mensaje **{{t:queue.statusCompleted}}** y haga clic en el botón **{{t:common.actions.close}}**.

![Fork completado](/assets/images/user-guide/49_repo_completed.png)
*(Figura 49: Operación fork completada exitosamente)*

> **Consejo**: Crear etiquetas en el formato de fecha y hora predeterminado es una buena práctica. La operación fork no afecta el repositorio original.

### 2.5.3 Up de Repositorio

![Repository up walkthrough](/assets/videos/user-guide/02-05-03-repository-up.webm)
*(Video: Starting a repository)*

Para activar el repositorio:

1. Seleccione el repositorio y siga la ruta **fx** > **up**.

![Operación Up](/assets/images/user-guide/50_repo_up.png)
*(Figura 50: Opción "up" del menú fx - iniciando el repositorio)*

2. Espere el mensaje **{{t:queue.statusCompleted}}**.

![Up completado](/assets/images/user-guide/51_repo_up_complete.png)
*(Figura 51: Inicio de repositorio completado)*

> **Consejo**: La operación "Up" inicia los servicios Docker definidos del repositorio.

### 2.5.4 Down de Repositorio

![Repository down walkthrough](/assets/videos/user-guide/02-05-04-repository-down.webm)
*(Video: Stopping a repository)*

Para detener un repositorio activo:

1. Seleccione el repositorio y siga la ruta **fx** > **down**.

![Operación Down](/assets/images/user-guide/52_down_button.png)
*(Figura 52: Opción "down" del menú fx - apagando el repositorio)*

2. Espere el mensaje **{{t:queue.statusCompleted}}**.

![Down completado](/assets/images/user-guide/53_down_completed.png)
*(Figura 53: Apagado de repositorio completado)*

> **Consejo**: La operación "Down" apaga el repositorio de forma segura. No se pierden datos, solo se detienen los servicios.

### 2.5.5 Deploy

![Repository deploy walkthrough](/assets/videos/user-guide/02-05-05-repository-deploy.webm)
*(Video: Deploying a repository)*

Para desplegar el repositorio en una ubicación diferente:

1. Seleccione el repositorio y siga la ruta **fx** > **deploy**.

![Operación Deploy](/assets/images/user-guide/54_deploy_button.png)
*(Figura 54: Opción "deploy" del menú fx)*

2. Introduzca la versión a desplegar en el campo **{{t:functions.functions.fork.params.tag.label}}**.
3. Seleccione las máquinas objetivo en el campo **{{t:functions.functions.backup_deploy.params.machines.label}}**.
4. Marque la opción **{{t:functions.checkboxOptions.overrideExistingFile}}** (si aplica).
5. Haga clic en el botón **{{t:common.actions.addToQueue}}**.

![Formulario de deploy](/assets/images/user-guide/55_deploy_form.png)
*(Figura 55: Configurando operación deploy - etiqueta, máquinas objetivo y opciones)*

6. Espere el mensaje **{{t:queue.statusCompleted}}**.

![Deploy completado](/assets/images/user-guide/56_deploy_completed.png)
*(Figura 56: Despliegue de repositorio completado)*

> **Consejo**: Después de que la operación deploy se complete, puede ejecutar el comando "up" para iniciar el repositorio en las máquinas objetivo.

### 2.5.6 Backup

![Repository backup walkthrough](/assets/videos/user-guide/02-05-06-repository-backup.webm)
*(Video: Backing up a repository)*

Para respaldar el repositorio:

1. Seleccione el repositorio y siga la ruta **fx** > **backup**.

![Operación Backup](/assets/images/user-guide/57_backup_button.png)
*(Figura 57: Opción "backup" del menú fx)*

2. Complete el formulario:
   - **{{t:functions.functions.fork.params.tag.label}}**: Introduzca un nombre descriptivo (por ejemplo, backup01012025)
   - **{{t:functions.functions.backup_create.params.storages.label}}**: Seleccione la ubicación del respaldo
   - **{{t:functions.checkboxOptions.overrideExistingFile}}**: Habilitar o deshabilitar la opción
   - **{{t:functions.functions.backup_deploy.params.checkpoint.label}}**: Revise la configuración

![Formulario de backup](/assets/images/user-guide/58_backup_form.png)
*(Figura 58: Formulario de configuración de backup - objetivo, nombre de archivo y opciones)*

3. Haga clic en el botón **{{t:common.actions.addToQueue}}**.

> **Consejo**: Use un nombre descriptivo para la etiqueta de backup. Considere habilitar checkpoint para repositorios grandes.

4. Espere el mensaje **{{t:queue.statusCompleted}}**.

![Backup completado](/assets/images/user-guide/59_backup_completed.png)
*(Figura 59: Tarea de backup completada exitosamente)*

> **Consejo**: Espere pacientemente antes de alcanzar el estado completado; los backups grandes pueden tomar varios minutos.

### 2.5.7 Aplicación de Plantilla

![Template application walkthrough](/assets/videos/user-guide/02-05-07-repository-templates.webm)
*(Video: Applying a template to a repository)*

Para aplicar una nueva plantilla al repositorio:

1. Seleccione el repositorio y siga la ruta **fx** > **{{t:resources.templates.selectTemplate}}**.

![Operación Templates](/assets/images/user-guide/60_templates_button.png)
*(Figura 60: Opción "Templates" del menú fx)*

2. Filtre las plantillas escribiendo en el cuadro de búsqueda.
3. Haga clic en la plantilla deseada para seleccionarla (la plantilla seleccionada está resaltada con un borde en negrita).
4. Haga clic en el botón **{{t:common.actions.addToQueue}}**.

![Formulario de selección de plantilla](/assets/images/user-guide/61_templates_form.png)
*(Figura 61: Buscando y seleccionando plantillas disponibles)*

> **Consejo**: Use el cuadro de búsqueda para encontrar rápidamente plantillas. Use "{{t:common.viewDetails}}" para conocer las características de la plantilla.

5. Espere el mensaje **{{t:queue.statusCompleted}}**.

![Plantilla aplicada](/assets/images/user-guide/62_templates_completed.png)
*(Figura 62: Aplicación de plantilla completada exitosamente)*

### 2.5.8 Unmount

![Repository unmount walkthrough](/assets/videos/user-guide/02-05-08-repository-unmount.webm)
*(Video: Unmounting a repository)*

Para desconectar el repositorio:

1. Seleccione el repositorio y siga la ruta **fx** > **{{t:common.actions.advanced}}** > **{{t:resources.repositories.unmount}}**.

![Operación Unmount](/assets/images/user-guide/63_unmount_button.png)
*(Figura 63: Opción "Unmount" en el menú avanzado)*

2. Espere el mensaje **{{t:queue.statusCompleted}}**.

![Unmount completado](/assets/images/user-guide/64_unmount_completed.png)
*(Figura 64: Operación Unmount completada)*

> **Consejo**: Asegúrese de que no haya operaciones activas en el repositorio antes de desmontarlo. Después de desmontar, el repositorio se vuelve inaccesible.

### 2.5.9 Expand

![Repository expand walkthrough](/assets/videos/user-guide/02-05-09-repository-expand.webm)
*(Video: Expanding repository size)*

Para aumentar el tamaño del repositorio:

1. Seleccione el repositorio y siga la ruta **fx** > **{{t:common.actions.advanced}}** > **{{t:functions.functions.repository_expand.name}}**.

![Operación Expand](/assets/images/user-guide/65_expand_button.png)
*(Figura 65: Opción "Expand" en el menú avanzado)*

2. Introduzca el tamaño deseado en el campo **{{t:functions.functions.repository_expand.params.size.label}}**.
3. Seleccione la unidad del menú desplegable de la derecha (GB, TB).
4. Haga clic en el botón **{{t:common.actions.addToQueue}}**.

![Formulario de expand](/assets/images/user-guide/66_expand_form.png)
*(Figura 66: Parámetro de nuevo tamaño para aumentar el tamaño del repositorio)*

> **Consejo**: No ingrese un valor menor que el tamaño actual. El servicio no se interrumpe durante la expansión del repositorio.

5. Espere el mensaje **{{t:queue.statusCompleted}}**.

![Expand completado](/assets/images/user-guide/67_expand_completed.png)
*(Figura 67: Expansión de repositorio completada)*

### 2.5.10 Rename

![Repository rename walkthrough](/assets/videos/user-guide/02-05-10-repository-rename.webm)
*(Video: Renaming a repository)*

Para cambiar el nombre del repositorio:

1. Seleccione el repositorio y siga la ruta **fx** > **{{t:common.actions.rename}}**.

![Operación Rename](/assets/images/user-guide/68_rename_button.png)
*(Figura 68: Opción "Rename" del menú fx)*

2. Ingrese el nuevo nombre del repositorio.
3. Haga clic en el botón **{{t:common.save}}**.

![Formulario de rename](/assets/images/user-guide/69_rename_form.png)
*(Figura 69: Diálogo para ingresar el nuevo nombre del repositorio)*

> **Consejo**: Los nombres de repositorio deben ser significativos para reflejar el tipo y propósito del repositorio. Evite caracteres especiales.

### 2.5.11 Eliminación de Repositorio

![Repository deletion walkthrough](/assets/videos/user-guide/02-05-11-repository-delete.webm)
*(Video: Deleting a repository)*

Para eliminar permanentemente el repositorio:

1. Seleccione el repositorio y siga la ruta **fx** > **{{t:resources.repositories.deleteRepository}}**.

![Operación Eliminar repositorio](/assets/images/user-guide/70_delete_repo_button.png)
*(Figura 70: Opción "Eliminar repositorio" del menú fx - rojo)*

2. Haga clic en el botón **{{t:common.delete}}** en la ventana de confirmación.

> **Advertencia**: La eliminación del repositorio es irreversible. Asegúrese de que los datos del repositorio estén respaldados antes de eliminarlo.

### 2.5.12 Detalles del Repositorio

![Repository details walkthrough](/assets/videos/user-guide/02-05-12-repository-details.webm)
*(Video: Viewing repository details)*

Para obtener información detallada sobre el repositorio:

1. Seleccione el repositorio.
2. Haga clic en el icono de ojo (**{{t:common.viewDetails}}**).

![Botón Ver Detalles](/assets/images/user-guide/71_repo_view_button.png)
*(Figura 71: Icono de ojo para abrir los detalles del repositorio)*

3. Revise la información en el panel de detalles:
   - **Nombre del repositorio** y tipo
   - **Equipo**: El equipo al que pertenece
   - **Máquina**: La máquina en la que está
   - **Versión de Vault**: Versión de cifrado
   - **GUID del repositorio**: Identificador único
   - **Estado**: Estado Montado/Desmontado
   - **Tamaño de imagen**: Tamaño total
   - **Última modificación**: Fecha de última modificación

![Panel de detalles del repositorio](/assets/images/user-guide/72_repo_details_view.png)
*(Figura 72: Información completa sobre el repositorio seleccionado)*

> **Consejo**: Toda la información mostrada en este panel es de referencia. Use las opciones del menú fx para operaciones de repositorio.

---

## 2.6 Operaciones de Conexión de Repositorio

Puede conectarse a los repositorios utilizando diferentes métodos.

### 2.6.1 Conexión de Aplicación de Escritorio

![Desktop connection walkthrough](/assets/videos/user-guide/02-06-01-desktop-connection.webm)
*(Video: Connecting via desktop application)*

1. Haga clic en el botón **{{t:resources.localActions.local}}** en la fila del repositorio.

![Botón de conexión local](/assets/images/user-guide/73_repo_connection_local.png)
*(Figura 73: Botón "Local" en la fila del repositorio - acceso a la aplicación de escritorio)*

2. Seleccione el método de acceso del menú desplegable:
   - **{{t:resources.localActions.openInDesktop}}**: Acceso con interfaz gráfica
   - **{{t:resources.localCommandBuilder.vscodeTab}}**: Abrir en editor de código
   - **{{t:common.terminal.terminal}}**: Acceso vía línea de comandos
   - **{{t:resources.localActions.showCLICommands}}**: Herramientas de línea de comandos

![Menú de opciones de conexión](/assets/images/user-guide/74_repo_connection.png)
*(Figura 74: Menú de conexión de repositorio - diferentes rutas de acceso)*

> **Consejo**: Si trabaja con VS Code, la opción "{{t:resources.localCommandBuilder.vscodeTab}}" proporciona la integración más rápida.

3. Haga clic en el botón **{{t:common.vscodeSelection.open}}** cuando el navegador solicite permiso.

![Permiso de apertura de aplicación de escritorio](/assets/images/user-guide/75_desktop_open_page.png)
*(Figura 75: Navegador solicitando permiso para abrir la aplicación de escritorio)*

> **Consejo**: Si no desea otorgar permiso cada vez que abra la aplicación de escritorio, marque la opción "Permitir siempre".

---

## 2.7 Configuración

Puede gestionar su perfil y configuración del sistema desde la sección Configuración.

### 2.7.1 Cambio de Contraseña

![Password change walkthrough](/assets/videos/user-guide/02-07-03-password-change.webm)
*(Video: Changing your password)*

1. Vaya a **{{t:common.navigation.settings}}** > **{{t:common.navigation.settingsProfile}}** desde el menú izquierdo.

![Página de configuración de perfil](/assets/images/user-guide/76_profiles_button.png)
*(Figura 76: Página Configuración → Perfil - configuración de vault personal)*

2. Haga clic en el botón **{{t:settings.personal.changePassword.submit}}**.

![Botón de cambiar contraseña](/assets/images/user-guide/77_profiles_change_button.png)
*(Figura 77: Botón "Change Password" en la sección de configuración personal)*

3. Ingrese su nueva contraseña. Requisitos de contraseña:
   - Al menos 8 caracteres de longitud
   - Debe contener letras mayúsculas y minúsculas
   - Debe contener al menos un número
   - Debe contener al menos un carácter especial

4. Vuelva a introducir la misma contraseña en el campo **{{t:settings.personal.changePassword.confirmPasswordLabel}}**.
5. Haga clic en el botón **{{t:settings.personal.changePassword.submit}}**.

![Formulario de cambio de contraseña](/assets/images/user-guide/78_profiles_change_form.png)
*(Figura 78: Formulario de cambio de contraseña - requisitos de seguridad visibles)*

> **Consejo**: Use combinaciones aleatorias al crear una contraseña segura.

---

## 2.8 Almacenamiento

La sección de Almacenamiento le permite gestionar las áreas físicas donde se almacenarán sus datos de respaldo.

### 2.8.1 Agregar Almacenamiento

![Storage creation walkthrough](/assets/videos/user-guide/02-08-01-storage-create.webm)
*(Video: Adding a storage location)*

1. Vaya a la pestaña **{{t:common.navigation.storage}}** desde el menú izquierdo.
2. Haga clic en el botón **{{t:resources.storage.createStorage}}**.

![Botón Add Storage](/assets/images/user-guide/79_storage_add_button.png)
*(Figura 79: Página de gestión de almacenamiento - botón "Add Storage")*

3. Complete el formulario:
   - **{{t:common.vaultEditor.fields.STORAGE.name.label}}**: Introduzca un nombre descriptivo
   - **{{t:common.vaultEditor.fields.STORAGE.provider.label}}**: Seleccione (por ejemplo, s3)
   - **{{t:common.vaultEditor.fields.STORAGE.description.label}}**: Agregue una descripción opcional
   - **{{t:common.vaultEditor.fields.STORAGE.noVersioning.label}}**: Opcional
   - **{{t:common.vaultEditor.fields.STORAGE.parameters.label}}**: banderas rclone (por ejemplo, --transfers 4)

![Formulario de creación de almacenamiento](/assets/images/user-guide/80_storage_form.png)
*(Figura 80: Formulario Add Storage - nombre, proveedor, descripción y parámetros)*

4. Haga clic en el botón **{{t:common.actions.create}}**.

> **Consejo**: Additional Parameters acepta banderas rclone para optimizar el rendimiento del almacenamiento.

---

## 2.9 Credenciales

La sección de Credenciales le permite gestionar de forma segura la información de acceso para sus repositorios.

### 2.9.1 Edición de Credenciales

![Credential editing walkthrough](/assets/videos/user-guide/02-09-01-credential-edit.webm)
*(Video: Editing credentials)*

1. Vaya a la pestaña **{{t:common.navigation.credentials}}** desde el menú izquierdo.
2. Seleccione el registro que desea editar.
3. Haga clic en el botón **{{t:common.actions.edit}}**.

![Lista de credenciales](/assets/images/user-guide/81_credentials.png)
*(Figura 81: Página de Credenciales - nombres de repositorio, equipos y botones de gestión)*

4. Cambie el **{{t:common.vaultEditor.fields.REPOSITORY.name.label}}** si es necesario.
5. Guarde con el botón **{{t:common.save}}**.

![Formulario de edición de credenciales](/assets/images/user-guide/82_credentials_form.png)
*(Figura 82: Formulario Editar nombre del repositorio - campos de configuración de vault)*

> **Consejo**: Las credenciales se almacenan cifradas y solo se descifran durante el despliegue.

### 2.9.2 Rastreo de Credenciales

![Credential trace walkthrough](/assets/videos/user-guide/02-09-02-credential-trace.webm)
*(Video: Viewing credential audit history)*

1. Seleccione el registro que desea rastrear.
2. Haga clic en el botón **{{t:common.actions.trace}}**.

![Botón de rastreo](/assets/images/user-guide/83_credentials_trace_button.png)
*(Figura 83: Botón "Trace" en la tabla de Credenciales)*

3. Revise el historial de auditoría.
4. Seleccione el formato desde el botón **{{t:common.actions.export}}**: **{{t:common.exportCSV}}** o **{{t:common.exportJSON}}**.

![Historial de auditoría de credenciales](/assets/images/user-guide/84_credentials_list_export.png)
*(Figura 84: Lista de credenciales - Opciones de exportación)*

> **Consejo**: La función de rastreo proporciona seguimiento del uso de credenciales para fines de auditoría de seguridad.

### 2.9.3 Eliminación de Credenciales

![Credential deletion walkthrough](/assets/videos/user-guide/02-09-03-credential-delete.webm)
*(Video: Deleting a credential)*

1. Seleccione el registro que desea eliminar.
2. Haga clic en el botón rojo **{{t:common.delete}}**.

![Botón de eliminar](/assets/images/user-guide/85_credentials_delete.png)
*(Figura 85: Botón rojo "Eliminar" en la página de Credenciales)*

3. Haga clic en el botón **{{t:common.delete}}** en la ventana de confirmación.

![Confirmación de eliminación](/assets/images/user-guide/86_credentials_delete_confirm.png)
*(Figura 86: Diálogo de confirmación de eliminación - advertencia de acción irreversible)*

> **Advertencia**: Antes de eliminar, asegúrese de que la credencial no se esté utilizando en otras máquinas o en otras operaciones. Asegúrese de tener una copia de seguridad de las credenciales críticas antes de eliminarlas.

---

## 2.10 Cola

La sección de Cola le permite rastrear las operaciones pendientes y completadas en el sistema.

### 2.10.1 Operaciones de Cola

![Queue operations walkthrough](/assets/videos/user-guide/02-10-01-queue-operations.webm)
*(Video: Managing queue operations)*

1. Haga clic en la pestaña **{{t:common.navigation.queue}}** desde el menú izquierdo.

![Página de cola](/assets/images/user-guide/87_queue_button.png)
*(Figura 87: Página de Cola - opciones de filtrado y pestañas de estado)*

2. Para filtrar elementos de la cola:
   - Use los filtros **{{t:queue.trace.team}}**, **{{t:queue.trace.machine}}**, **{{t:queue.trace.region}}** y **{{t:queue.trace.bridge}}**
   - Especifique el **{{t:system.audit.filters.dateRange}}**
   - Marque la opción **{{t:queue.filters.onlyStale}}**

3. Vea los detalles en las pestañas de estado:
   - **{{t:queue.statusActive}}**: Tareas que se están procesando
   - **{{t:queue.statusCompleted}}**: Tareas completadas exitosamente
   - **{{t:queue.statusCancelled}}**: Tareas canceladas
   - **{{t:queue.statusFailed}}**: Tareas fallidas

4. Seleccione un formato desde el botón **{{t:common.actions.export}}**: **{{t:common.exportCSV}}** o **{{t:common.exportJSON}}**.

![Exportación de cola](/assets/images/user-guide/88_queue_export.png)
*(Figura 88: Lista de cola - Opciones de exportación)*

> **Consejo**: La opción "{{t:queue.filters.onlyStale}}" ayuda a encontrar tareas que han estado procesándose durante mucho tiempo. Exporte regularmente el historial de cola para analizar las tendencias de ejecución de tareas.

---

## 2.11 Auditoría

La sección de Auditoría mantiene registros de todas las operaciones realizadas en el sistema.

### 2.11.1 Registros de Auditoría

![Audit records walkthrough](/assets/videos/user-guide/02-11-01-audit-records.webm)
*(Video: Viewing system audit records)*

1. Haga clic en la pestaña **{{t:common.navigation.audit}}** desde el menú izquierdo.

![Lista de auditoría](/assets/images/user-guide/89_audit_list.png)
*(Figura 89: Página de Auditoría - registro detallado de todas las operaciones del sistema)*

2. Filtre los registros de auditoría:
   - **Rango de fechas**: Filtrar por un período específico
   - **Tipo de entidad**: Filtrar por Request, Machine, Queue, etc.
   - **Buscar**: Realizar búsqueda de texto

3. Revise la información de cada registro:
   - **Marca de tiempo**: Fecha y hora de la operación
   - **Acción**: Tipo de operación (Crear, Editar, Eliminar, etc.)
   - **Tipo de entidad**: Tipo de objeto afectado
   - **Nombre de entidad**: Identificador específico del objeto
   - **Usuario**: Usuario que realizó la operación
   - **Detalles**: Información adicional sobre la operación

4. Seleccione un formato desde el botón **{{t:common.actions.export}}**: **{{t:common.exportCSV}}** o **{{t:common.exportJSON}}**.

![Exportación de auditoría](/assets/images/user-guide/90_audit_export.png)
*(Figura 90: Exportación de registro de auditoría - opciones CSV y JSON)*

> **Consejo**: El registro de auditoría es crítico para rastrear toda la actividad del sistema con fines de seguridad y cumplimiento. Exporte regularmente el registro de auditoría y guárdelo en una ubicación segura.

---

**© 2025 Rediacc Platform – All Rights Reserved.**
