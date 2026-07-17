---
title: Web-Konsole
description: Die gesamte rdc-CLI aus dem Browser heraus bedienen, mit Formularen, Ressourcen-Auswahlfeldern und Ausführungsverlauf
category: Guides
order: 8
language: de
sourceHash: "b735dd2fd77435c5"
sourceCommit: "5197d1c0349438c2bff2442377a5166d0b8214b6"
---

# Web-Konsole

Die Web-Konsole ist eine Browser-Oberfläche für die gesamte `rdc`-CLI. Jeder CLI-Befehl erscheint in der Konsole mit einem Formular, Validierung, Ressourcen-Auswahlfeldern und einem Ausführen-Button. Es gibt keinen separaten "Web-Funktionsumfang": Die Konsole wird aus dem CLI-Vertrag generiert, sodass jeder Befehl der CLI auch in der Konsole vorhanden ist und neue Befehle automatisch auftauchen.

Sie finden sie im Webportal unter `/account/console`.

## Verfügbarkeit

Die Web-Konsole ist eine kostenpflichtige Funktion. Sie ist in den bezahlten Plänen enthalten und im Community-Plan ausgeblendet. Der Zugriff ist außerdem rollenbasiert, sodass ein Organisationsadministrator steuern kann, wer sie zu sehen bekommt.

## Verhältnis zum Konfigurationsspeicher

Die Konsole liest Ihre Ressourcen (Maschinen, Repositories und so weiter) aus Ihrem verschlüsselten Konfigurationsspeicher und entschlüsselt diese Konfiguration ausschließlich im Browser. Das bedeutet:

- **Im gesperrten Zustand** können Sie trotzdem den gesamten Befehlskatalog durchstöbern, das Formular jedes Befehls öffnen und dessen Parameter lesen. Das funktioniert ohne jede Einrichtung.
- **Um Befehle auszuführen und Auswahlfelder zu nutzen**, entsperren Sie zunächst Ihren Konfigurationsspeicher (Passkey, Master-Passwort oder Wiederherstellungscode, siehe [Konfigurationsspeicher](/de/docs/config-storage)). Ausführen-Buttons, Ressourcenseiten und Ressourcen-Auswahlfelder hängen allesamt von der entsperrten Sitzung ab.

Der entschlüsselte Schlüssel bleibt ausschließlich im Speicher des Browsers. Ein Neuladen der Seite sperrt die Konsole wieder, und nach 30 Minuten Inaktivität sperrt sie sich automatisch.

## Ressourcen-Auswahlfelder

Nach dem Entsperren ersetzen die Befehlsformulare Freitextfelder durch Auswahlfelder, die aus Ihrer entschlüsselten Konfiguration gespeist werden: Maschinen, Repositories, Datastores, Storages, Cluster, Cloud-Provider und Backup-Strategien. Manche Auswahlfelder werden stattdessen live aufgelöst, indem ein Befehl ausgeführt wird, etwa Container auf einer Maschine oder Snapshots in einem Datastore.

Die Auswahlfelder filtern voneinander abhängig: Wählen Sie eine Maschine, grenzt sich das Repository-Auswahlfeld auf diese Maschine ein. Für Repository-Referenzen setzt ein Referenz-Builder die vollständige Form `name:tag@machine` aus den einzelnen Auswahlen zusammen. Die Auswahlfelder sind Hinweise, keine Zwänge - Sie können jederzeit einen Wert manuell eingeben.

## Befehle ausführen

Der Browser besitzt niemals einen SSH-Schlüssel oder eine Maschinenadresse. Klicken Sie auf Ausführen, sendet die Konsole nur die Befehlsabsicht - welcher Befehl und welche Parameter -, und ein Executor löst alles Weitere auf und führt es aus. Wie das funktioniert und welche Befehle auf diesem Weg laufen können, steht unter [Proxy & Executor](/de/docs/proxy-and-executor).

Befehle, die nur Ihre Konfiguration bearbeiten (zum Beispiel einen Maschinen-Eintrag anlegen), laufen überhaupt nicht remote. Die Konsole leitet sie an den eingebauten Konfigurationseditor weiter, wo die Änderung verschlüsselt und wie jede andere Konfigurationsänderung übertragen wird.

Jedes Formular zeigt außerdem die entsprechende CLI-Befehlszeile an, sodass sich alles, was Sie in der Konsole einrichten, direkt in ein Terminal oder ein Skript kopieren lässt.

## Orientierung in der Konsole

- **Ressourcenseiten**: Maschinen, Repositories und Jobs haben jeweils Listen- und Detailseiten, mit den passenden Befehlen als Aktionen.
- **Befehlspalette**: Drücken Sie Cmd-K (Ctrl-K), um direkt zu einem Befehl oder einer Ressource nach Namen zu springen.
- **Ausführungsverlauf**: Vergangene Ausführungen bleiben pro Sitzung erhalten, sodass Sie die Ausgabe prüfen und mit denselben Parametern erneut ausführen können.

## Verwandte Seiten

- [Konfigurationsspeicher](/de/docs/config-storage), den verschlüsselten Konfigurationsspeicher einrichten und entsperren
- [Proxy & Executor](/de/docs/proxy-and-executor), das Ausführungsmodell hinter dem Ausführen-Button
