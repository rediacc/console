---
title: "Kontoverwaltung"
description: "Organisationen, Teams, Mitglieder und Abonnements für Ihr Rediacc-Konto verwalten."
category: Guides
order: 12
language: de
sourceHash: "e32952a1485133e0"
sourceCommit: "a97009927c347f7090e4f4f60f3948997654ae4b"
---

### Organisationen

Bei der Registrierung erstellt Rediacc automatisch eine Organisation für Sie. Ihre Organisation ist der übergeordnete Container für alle Ressourcen -- Maschinen, Repositories, Abonnements und Teammitglieder.

![Registration Flow](/img/account-registration-flow.svg)

Jede Organisation hat:
- Einen eindeutigen Namen (standardmäßig Ihre E-Mail-Adresse)
- Einen Abonnementplan (beginnt mit COMMUNITY)
- Ein Standardteam (alle Mitglieder treten automatisch bei)

### Mitglieder & Rollen

Organisationen unterstützen drei Rollen:

![Role Hierarchy](/img/account-role-hierarchy.svg)

| Rolle | Fähigkeiten |
|-------|-------------|
| **Owner** | Volle Kontrolle: Abrechnung, Eigentumsübertragung, Verwaltung aller Mitglieder und Teams |
| **Admin** | Mitglieder einladen und entfernen, Teams erstellen und verwalten, API-Token widerrufen |
| **Member** | Organisationsdaten einsehen, API-Token erstellen, zugewiesene Teams nutzen |

Mitglieder einladen:
```bash
# Über das Portal: Organisation > Mitglieder > Einladen
# Oder über die API
```

Wenn ein Mitglied entfernt wird, werden seine API-Token und Config-Storage-Token automatisch widerrufen.

### Teams

Mit Teams können Sie Ressourcen innerhalb einer Organisation eingrenzen. Jede Organisation beginnt mit einem Standardteam.

![Team Structure](/img/account-team-structure.svg)

Team-Rollen:
- **Team Admin**: Kann Teammitglieder innerhalb des Teams hinzufügen/entfernen
- **Member**: Kann auf teamspezifische Ressourcen zugreifen

Organisationseigentümer und Admins haben automatisch Zugriff auf alle Teams ohne explizite Mitgliedschaft.

### Abonnements & Pläne

Rediacc bietet vier Pläne:

| Plan | Maschinen | Repo-Lizenzen/Monat | Delegierungszert. Standard / Max | Funktionen |
|------|-----------|----------------------|----------------------------------|------------|
| COMMUNITY | 2 | 500 | 15d / 30d | Basis |
| PROFESSIONAL | 5 | 5.000 | 60d / 120d | Berechtigungsgruppen, Audit-Log, individuelles Branding, vorrangiger Support |
| BUSINESS | 20 | 20.000 | 90d / 180d | Ceph, erweiterte Analysen, Warteschlangen-Priorität, erweiterte Warteschlange |
| ENTERPRISE | 50 | 100.000 | 120d / 365d | Dedizierter Account Manager |

![Subscription Flow](/img/account-subscription-flow.svg)

Alle Pläne beginnen mit einer 3-tägigen Übergangszeit. Maschinenaktivierungen werden pro Team verfolgt und nach Inaktivität automatisch freigegeben. Siehe [Abonnement & Lizenzierung](/de/docs/subscription-licensing) für das vollständige Maschinen- vs. Repo-Lizenz-Modell.

### Abrechnung

Nur der **Owner** der Organisation kann die Abrechnung verwalten:
- Eine Stripe-Checkout-Sitzung für Plan-Upgrades erstellen
- Auf das Stripe-Abrechnungsportal für Änderungen der Zahlungsmethode zugreifen
- Self-Service-Rückerstattungen anfordern (innerhalb von 14 Tagen, mit 30 Tagen Abklingzeit)

### Datenregion

Ihr Konto wird in der Datenregion gespeichert, die Sie bei der Registrierung ausgewählt haben (EU, USA oder Asien-Pazifik). Diese Wahl ist dauerhaft. Das Regions-Badge im Portal zeigt an, in welcher Region Ihre Daten gespeichert sind. Siehe [Datenregionen](/en/docs/data-regions) für Details.

### Edge-Kanal

Wenn Ihr Konto sich im Edge-Kanal befindet, wird im Portal-Seitenmenü ein "Edge"-Badge angezeigt. Edge-Konten haben 2-fache Community-Limits, aber keinen Zugang zu kostenpflichtigen Plänen. Siehe [Release-Kanäle](/en/docs/release-channels) für die Unterschiede zwischen Edge und Stable.

### Delegierungszertifikate

Für On-Premise- und Air-Gapped-Deployments können Sie Ihre Delegierungszertifikate im Kundenportal unter **/account/delegation-certs** verwalten. Die Seite ist für alle Kunden unabhängig vom Plan sichtbar; nur die Standard-Gültigkeitsdauern unterscheiden sich je nach Plan.

#### Rollenzugriff

| Aktion | Org Owner | Org Admin | Member |
|--------|-----------|-----------|--------|
| Zertifikate auflisten / anzeigen / herunterladen | ✓ | ✓ | ✓ |
| Neues Zertifikat erstellen | ✓ | ✓ | ✗ |
| Zertifikat widerrufen | ✓ | ✓ | ✗ |
| Auto-Erneuerungs-Token ausstellen | ✓ | ✓ | ✗ |
| Air-Gapped-Erneuerungsanfrage verarbeiten | ✓ | ✓ | ✗ |

Members können die Liste einsehen und vorhandene Zertifikate herunterladen (nützlich für die Verteilung des Zertifikats auf eine Gruppe von Maschinen), aber nur Owner und Admins können Zertifikate ausstellen oder widerrufen.

#### Einzelaktiv-Durchsetzung

Ein Abonnement darf nur **ein aktives Delegierungszertifikat gleichzeitig** haben. Jede On-Premise-Installation setzt pro Monat und pro Maschine Quoten gegen ihr eigenes lokales Ledger durch; mehrere aktive Zertifikate würden das effektive Kontingent vervielfachen, ohne dass eine Abstimmung möglich wäre.

Wenn Sie versuchen, ein zweites Zertifikat zu erstellen, während bereits eines aktiv ist, zeigt das Portal einen Dialog mit zwei Optionen:

- **Erneuern (empfohlen)** - verlängert die bestehende Kette. Alle zuvor ausgestellten Repo-Lizenzen funktionieren weiterhin unter dem erneuerten Zertifikat. Verwenden Sie diese Option, wenn Sie ein ablaufendes Zertifikat auf derselben On-Premise-Installation rotieren.
- **Widerrufen und neu erstellen** - verwirft die bestehende Kette und beginnt neu ab Genesis. Zuvor ausgestellte Repo-Lizenzen werden nicht mehr verifizierbar, sobald die `validUntil`-Frist des alten Zertifikats verstrichen ist. Verwenden Sie diese Option nur, wenn Sie zu einer neuen On-Premise-Installation mit einem anderen Signing-Key migriert sind oder sich von einem kompromittierten Key erholen.

Wenn Sie separate Umgebungen benötigen (Produktion + Staging + DR + Multi-Region), erwerben Sie ein Abonnement pro Installation.

#### Auto-Erneuerungs-Bootstrap

Um die automatische On-Premise-Erneuerung zu aktivieren, klicken Sie auf der Seite "Delegation Certs" auf **Auto-Erneuerungs-Token abrufen**. Dadurch wird ein `delegation:renew`-bereichsspezifisches API-Token (permanent, kein Ablauf) ausgestellt und die Werte angezeigt, die Sie in Ihre On-Premise-`.env` einfügen müssen:

```
UPSTREAM_URL=https://www.rediacc.com
UPSTREAM_API_KEY=rdt_<token>
```

Das Token gewährt **ausschließlich** die Erneuerung von Delegierungszertifikaten - es kann keine anderen Ressourcen lesen oder ändern. Dies ist der einzige Weg, ein `delegation:renew`-Token auszustellen; der reguläre `/portal/api-tokens`-Ablauf schließt diesen Geltungsbereich nicht ein.

#### Air-Gapped-Erneuerung

Wenn Ihre On-Premise-Installation keinen ausgehenden HTTPS-Zugang hat, verwenden Sie den Offline-Manifest-Ablauf:

1. Klicken Sie auf der On-Premise-Adminseite auf **Erneuerungsanfrage herunterladen**. Die On-Premise-Installation erzeugt ein signiertes Manifest mit dem lokalen Chain-Head.
2. Übertragen Sie das Manifest zum Upstream (USB, verschlüsselte E-Mail oder ein beliebiger Kanal).
3. Klicken Sie im Upstream-Portal auf **Erneuerungsanfrage hochladen** und wählen Sie das Manifest aus. Der Upstream verifiziert die Manifest-Signatur, stellt ein neues Zertifikat aus und gibt es als herunterladbare `.json`-Datei zurück.
4. Übertragen Sie das neue Zertifikat zurück zur On-Premise-Installation und laden Sie es über die On-Premise-Adminseite hoch.

Der Upstream lehnt Manifeste ab, die älter als 7 Tage sind. Siehe [On-Premise-Installation](/en/docs/on-premise) für die vollständige Schritt-für-Schritt-Einrichtung und [Lizenzkette & Delegierung](/en/docs/license-chain) für das kryptografische Design.

#### Rate-Limit

Die Zertifikatserstellung ist auf **10 Versuche pro 24-Stunden-Fenster** pro Abonnement begrenzt, einschließlich fehlgeschlagener Versuche (Kollisionsspam, ungültige Eingaben). Wenn Sie das Limit erreichen, zeigt das Portal einen `Retry-After`-Wert an, der angibt, wann Sie es erneut versuchen können.
