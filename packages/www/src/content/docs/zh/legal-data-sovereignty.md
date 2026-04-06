---
title: "数据主权"
description: "Rediacc 的自托管架构如何满足全球各司法管辖区的数据驻留和主权要求。"
category: "Legal"
order: 7
language: zh
sourceHash: "72bbd6b951067a1d"
---

许多国家要求其公民的个人数据在国境内存储和处理。Rediacc 的自托管架构在设计上满足这些要求：数据保留在您的机器上、您的数据中心、您的管辖区内。克隆期间数据不会离开机器，也没有第三方 SaaS 处理您的数据。

## 为什么自托管解决数据主权问题

跨境数据传输是云计算中最困难的合规问题。每个管辖区都有不同的规则、充分性决定和传输机制。自托管消除了整个类别：

- **无跨境传输**：CoW 克隆（`cp --reflink=always`）在同一机器上复制数据
- **无第三方处理者**：Rediacc 在您的基础设施上运行，而非 Rediacc 的服务器
- **无需充分性评估**：数据从不离开管辖区，传输规则不适用
- **无标准合同条款**：没有需要监管的国际数据流

## 管辖区覆盖

### 欧盟

[GDPR](https://gdpr-info.eu/) 限制将个人数据传输到欧盟/EEA 以外，除非目的地提供充分保护。Schrems II 裁决使欧美隐私盾无效，[Meta 被罚 12 亿欧元](https://www.dataprotection.ie/en/news-media/press-releases/Data-Protection-Commission-announces-conclusion-of-inquiry-into-Meta-Ireland)展示了跨境传输错误的代价。

在欧盟部署的自托管 Rediacc 将所有数据保留在欧盟境内。不需要传输机制。条款级映射请参见 [GDPR 合规](/zh/docs/legal-gdpr)。

### 中国

[《个人信息保护法》(PIPL)](http://www.npc.gov.cn/npc/c30834/202108/a8c4e3672c74491a80b53a172bb753fe.shtml) 要求中国公民的个人数据存储在中国境内。跨境传输需要网信办 (CAC) 安全评估。中国基础设施上的自托管 Rediacc 完全避免 CAC 安全评估。

### 巴西

[LGPD](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm) 要求充分的安全措施并限制国际传输。在巴西自托管消除了传输顾虑，并通过 LUKS2 加密和网络隔离满足第 46 条的技术措施要求。

### 印度

[DPDP 法案（2023）](https://www.meity.gov.in/content/digital-personal-data-protection-act-2023)限制向不在政府批准列表中的国家传输。在印度基础设施上自托管意味着无论哪些国家被列入黑名单都不会发生传输。印度的政府和国防部门强烈偏好本地部署方案。

### 土耳其

[KVKK（第 6698 号法律）](https://kvkk.gov.tr/en/)以复杂的充分性要求限制国际传输。土耳其不在欧盟充分性列表上，因此跨境传输需要明确批准。在土耳其自托管完全消除了这一问题。

### 韩国

[PIPA](https://www.pipc.go.kr/eng/index.do) 是全球最严格的法律之一，明确要求在存储和传输过程中加密个人数据。LUKS2 AES-256 直接满足此要求。罚款最高可达收入的 3%。

### 日本

[APPI](https://www.ppc.go.jp/en/legal/) 限制跨境传输，除非接收国提供充分保护。在日本自托管避免了传输限制，并符合市场对本地部署方案的文化偏好。

### 澳大利亚

[《1988 年隐私法》](https://www.legislation.gov.au/C2004A03712/latest/text)要求披露实体对海外接收方的数据处理承担责任（APP 8）。自托管完全消除了这一责任。LUKS2 加密和网络隔离在 APP 11 下提供了具体的"合理步骤"。

### 阿联酋

[联邦法令第 45/2021 号](https://u.ae/en/about-the-uae/digital-uae/data/data-protection-laws)要求充分的安全措施并限制跨境传输。阿联酋的政府和金融部门强烈偏好本地部署。

### 沙特阿拉伯

[PDPL](https://sdaia.gov.sa/en/SDAIA/about/Documents/Personal%20Data%20English%20V2.pdf) 要求沙特居民的个人数据在沙特阿拉伯境内存储和处理。自托管直接满足这一严格的本地化要求。

### 新加坡

[PDPA](https://sso.agc.gov.sg/Act/PDPA2012) 要求合理的安全性并限制跨境传输。在新加坡（主要的 APAC 数据枢纽）自托管可满足东盟运营的区域合规要求。

### 俄罗斯

[联邦法律 242-FZ](https://pd.rkn.gov.ru/) 要求俄罗斯公民的个人数据存储在俄罗斯境内的服务器上。违规可导致网站被封锁。在俄罗斯领土上自托管通过架构提供合规。

## 模式

在所有管辖区中，合规等式相同：

| 属性 | 云/SaaS | 自托管 Rediacc |
|------|--------|---------------|
| 数据位置 | 提供商的数据中心（可能跨境） | 您的机器，您的管辖区 |
| 需要传输机制 | 是（SCC、充分性、同意） | 否（不发生传输） |
| 第三方处理者责任 | 是 | 否 |
| 加密控制 | 提供商管理的密钥 | 您的 LUKS 凭据，本地存储 |
| 克隆/暂存数据 | 可能跨境或脱离您的控制 | 同一机器上的 CoW，同一管辖区 |
