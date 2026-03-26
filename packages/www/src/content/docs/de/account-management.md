---
title: Kontoverwaltung
description: Organisationen, Teams, Mitglieder und Abonnements in Rediacc.
category: Guides
order: 12
language: de
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
# From the portal: Organization > Members > Invite
# Or via API
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

| Plan | Maschinen | Repo-Lizenzen/Monat | Funktionen |
|------|-----------|----------------------|------------|
| COMMUNITY | 2 | 500 | Basis |
| PROFESSIONAL | 10 | 2.000 | Berechtigungsgruppen, Warteschlangen-Priorität |
| BUSINESS | 25 | 5.000 | Ceph, erweiterte Analysen, Audit-Log |
| ENTERPRISE | Unbegrenzt | Unbegrenzt | Individuelles Branding, dediziertes Konto |

![Subscription Flow](/img/account-subscription-flow.svg)

Alle Pläne beginnen mit einer 3-tägigen Übergangszeit. Maschinenaktivierungen werden pro Team verfolgt und nach Inaktivität automatisch freigegeben.

### Abrechnung

Nur der **Owner** der Organisation kann die Abrechnung verwalten:
- Eine Stripe-Checkout-Sitzung für Plan-Upgrades erstellen
- Auf das Stripe-Abrechnungsportal für Änderungen der Zahlungsmethode zugreifen
- Self-Service-Rückerstattungen anfordern (innerhalb von 14 Tagen, mit 30 Tagen Abklingzeit)
