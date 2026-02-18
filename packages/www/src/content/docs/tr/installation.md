---
title: "Kurulum"
description: "Rediacc CLI'i Linux, macOS veya Windows uzerine kurun."
category: "Guides"
order: 1
language: tr
---

# Kurulum

`rdc` CLI'ı iş istasyonunuza kurun. Manuel olarak kurmanız gereken tek araç budur -- diğer her şey uzak makineleri kurduğunuzda otomatik olarak halledilir.

## Linux ve macOS

Kurulum betiğini çalıştırın:

```bash
curl -fsSL https://get.rediacc.com | sh
```

Bu komut `rdc` ikili dosyasını `$HOME/.local/bin/` dizinine indirir. Bu dizinin PATH değişkeninizde olduğundan emin olun:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Kalıcı hale getirmek için bu satırı kabuk profilinize (`~/.bashrc`, `~/.zshrc`, vb.) ekleyin.

## Windows

PowerShell'de kurulum betiğini çalıştırın:

```powershell
irm https://www.rediacc.com/install.ps1 | iex
```

Bu, `rdc.exe` dosyasını `%LOCALAPPDATA%\rediacc\bin\` dizinine indirir. Bu dizinin PATH'inizde olduğundan emin olun. Yükleyici, henüz eklenmemişse eklemenizi isteyecektir.

## Kurulumu Doğrulama

```bash
rdc --version
```

Kurulu sürüm numarasını görmelisiniz.

## Güncelleme

`rdc` aracını en son sürüme güncellemek için:

```bash
rdc update
```

Kurmadan güncellemeleri kontrol etmek için:

```bash
rdc update --check-only
```

Bir güncellemeden sonra önceki sürüme geri dönmek için:

```bash
rdc update rollback
```
