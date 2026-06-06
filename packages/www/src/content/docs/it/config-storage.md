---
title: Archivio di Configurazione
description: Sincronizzazione cifrata zero-knowledge della configurazione con cifratura basata su passkey
category: Guides
order: 8
language: it
sourceHash: "daf79946b8925246"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Archivio di Configurazione

L'archivio di configurazione fornisce la sincronizzazione cifrata zero-knowledge della tua configurazione CLI tra dispositivi. Le configurazioni sono cifrate con chiavi derivate dalla tua passkey; il server non vede mai i dati in testo in chiaro.

## Prerequisiti

- **Autenticazione a due fattori** abilitata sull'account
- **Provider di passkey con supporto PRF**: chiave di sicurezza FIDO2 (ad es. YubiKey), iCloud Keychain, Google Password Manager, 1Password o Dashlane
- **Browser**: Chrome 133+, Edge 133+, Firefox 130+ o Safari 17+

## Configurazione

1. Vai ad **Archivio di Configurazione** nella barra laterale, poi fai clic su **Configura Archivio di Configurazione**
2. La checklist dei requisiti verifica il browser, il 2FA e lo stato della sessione
3. Fai clic su **Avvia Configurazione**; dovrai toccare la tua chiave di sicurezza due volte:
   - Primo tocco: registra la passkey
   - Secondo tocco: deriva le chiavi di cifratura tramite PRF
4. Configurazione completata; il segreto della passkey è memorizzato nel portachiavi del sistema operativo

Dopo la configurazione, le operazioni CLI quotidiane (push/pull) funzionano senza la passkey. Avvertenza: la configurazione richiede una passkey con supporto dell'estensione PRF. Non tutti i token hardware o gli autenticatori di piattaforma dispongono di essa.

## Compatibilità dei Provider PRF

| Provider | Supporto PRF | Piattaforme |
|----------|:-----------:|-----------|
| YubiKey / chiavi di sicurezza FIDO2 | ✅ | Windows 11, macOS, Linux |
| iCloud Keychain | ✅ | macOS 15+, iOS 18+ |
| Google Password Manager | ✅ | Android |
| 1Password | ✅ | Android, iOS |
| Dashlane | ✅ | Multipiattaforma |
| Estensione Bitwarden | ❌ | In sviluppo |
| Windows Hello | ❌ | Non supportato |

## Gestione dei Membri

L'archivio di configurazione ha scope per organizzazione. I membri vengono gestiti tramite il portale web:

- **Visualizza i membri**: Archivio di Configurazione > Membri
- **Aggiungi un membro**: attualmente solo tramite CLI (UI web pianificata)
- **Rimuovi un membro**: fai clic sul pulsante di rimozione nella pagina Membri (richiede 2FA + ri-autenticazione)

Le protezioni di sicurezza impediscono di rimuovere l'ultimo membro attivo o di rimuovere se stessi.

## Sicurezza

- **Zero-knowledge**: il server memorizza dati con tripla cifratura che non riesce a decifrare
- **Chiave divisa**: la decifratura richiede sia il segreto della passkey (client) che il segreto del server
- **Token rotanti**: ogni chiamata API usa un token fresco; i vecchi token si autodistruggono
- **Binding IP**: i token sono legati al tuo IP al primo utilizzo
- **Revoca istantanea**: i membri rimossi perdono l'accesso entro 30 secondi

## Risoluzione dei Problemi

| Errore | Causa | Soluzione |
|-------|-------|-----|
| PRF non supportato | L'autenticatore non ha l'estensione PRF | Usare YubiKey, iCloud Keychain, 1Password o Dashlane |
| X25519 non supportato | Versione del browser troppo vecchia | Aggiornare a Chrome 133+, Edge 133+, Firefox 130+ o Safari 17+ |
| Già configurato | L'archivio esiste per la tua organizzazione | Visitare /account/config-storage per gestirlo |
| Archivio di configurazione non configurato | Blob storage mancante sul server | Contattare il proprio amministratore per configurare R2/RustFS |
| Token scaduto | Nessuna attività per 24 ore | Eseguire qualsiasi comando dell'archivio di configurazione per aggiornare |
| Impossibile rimuovere l'ultimo membro | Bloccherebbe permanentemente l'archivio | Aggiungere prima un altro membro |
