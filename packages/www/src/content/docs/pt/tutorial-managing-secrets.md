---
title: "Gerir Segredos"
description: "Coloque credenciais de implementação num lugar a que os forks não conseguem aceder. Apenas escrita por design."
category: "Tutorials"
subcategory: advanced
order: 8
language: pt
sourceHash: "0b4d72c80b489e12"
---

# Gerir Segredos

As aplicações reais precisam de credenciais reais: uma chave Stripe de produção, uma palavra-passe de base de dados, um token de API. O lugar errado para as colocar é no repositório, porque um fork herda tudo o que está dentro da imagem encriptada -- e de repente o seu sandbox está a cobrar cartões de clientes reais.

O lugar certo é `rdc repo secret`. Dois modos de entrega, apenas escrita por design, e o fork começa sem nada.

## Ver o tutorial

![Tutorial: Managing secrets](/assets/tutorials/tutorial-managing-secrets.cast)

## A armadilha: `.env` no repositório

![A .env file inside the repo image gets cloned by every fork](/img/tutorials/tutorial-managing-secrets/slide-1.svg)

A maioria das equipas coloca `.env` no repositório. É o movimento óbvio.

Depois fazem um fork.

O fork é uma cópia byte-a-byte da imagem do pai. O que quer que esteja em `.env` está no `.env` do fork. Os contentores do fork arrancam. Leem a mesma chave Stripe. Chamam a mesma API Stripe -- com credenciais de produção. Do ponto de vista do Stripe, essa chamada é *você*.

É um mau dia.

## Definir um segredo

A solução é `rdc repo secret`. Defina um no modo `env` -- fica disponível como variável de ambiente no contentor:

```bash
time rdc repo secret set --name my-app --key DB_HOST --value postgres.internal --mode env --current ""
```

Dois aspetos a notar:

- `--mode env`. O valor fica disponível como variável de ambiente.
- `--current ""`. String vazia. Estamos a declarar que este é um segredo novo sem valor anterior.

Defina outro, no modo `file` -- para qualquer coisa sensível:

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_xxx --mode file --current ""
```

O modo `file` nunca coloca o valor no ambiente do contentor. Escreve-o em `/run/secrets/stripe_key` -- o mecanismo padrão do Docker.

Liste o que tem:

```bash
time rdc repo secret list --name my-app
```

Vê nomes e modos. **Sem valores.** A lista nunca mostra valores.

## Integrar no compose

Abra `docker-compose.yml`. Referencie ambos os modos:

```yaml
services:
  api:
    image: myapp:latest
    environment:
      DATABASE_HOST: ${REDIACC_SECRET_DB_HOST}
    secrets:
      - stripe_key

secrets:
  stripe_key:
    file: /var/run/rediacc/secrets/${REDIACC_NETWORK_ID}/STRIPE_KEY
```

`${REDIACC_SECRET_DB_HOST}` é o modo `env` -- o wrapper compose do `renet` expande-o a partir do seu armazenamento de segredos no momento da implementação.

O bloco `secrets:` é o modo `file` -- o mecanismo padrão do Docker. O caminho do anfitrião usa `${REDIACC_NETWORK_ID}` para que o mesmo compose funcione para pais e forks. Cada fork tem o seu próprio ID de rede.

Implemente:

```bash
time rdc repo up --name my-app -m my-server
```

## Verificar no contentor

Ambos os modos devem estar disponíveis dentro do contentor agora. Verifique o segredo no modo env:

```bash
time rdc term connect -m my-server -r my-app -c 'docker exec $(docker ps -q -f name=api) printenv DATABASE_HOST'
```

`postgres.internal` -- o segredo em modo env chegou ao ambiente do contentor.

Agora o de modo file:

```bash
time rdc term connect -m my-server -r my-app -c 'docker exec $(docker ps -q -f name=api) cat /run/secrets/stripe_key'
```

`sk_test_xxx` -- o ficheiro está montado via o mecanismo padrão de segredos do Docker.

## Nunca o pode ler de volta

![Write-only model: get returns a digest, never the value](/img/tutorials/tutorial-managing-secrets/slide-2.svg)

Agora a parte que surpreende as pessoas:

```bash
time rdc repo secret get --name my-app --key STRIPE_KEY
```

Obtém um digest. **Não o valor.** Não existe nenhum sinalizador que faça devolver o valor. Não há nenhum comando em lado algum que lhe dê o texto simples de volta.

É o modelo do GitHub Actions: apenas escrita. Pode provar que sabe qual é um segredo passando `--current <value>` e vendo a pré-condição passar. Não pode pedir ao Rediacc para lhe dizer o que é.

Perdeu o valor? **Não espie. Faça rotação.**

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_new --mode file --rotate-secret
```

`--rotate-secret` ignora a pré-condição. O registo de auditoria marca-o como uma rotação -- explícito, deliberado.

Se ainda se lembrar do valor antigo, prove-o em vez disso:

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_new --mode file --current sk_test_xxx
```

É o caminho mais seguro -- apanha o erro de "estou no terminal errado".

## A conclusão do fork

![After fork, the secrets list is empty](/img/tutorials/tutorial-managing-secrets/slide-3.svg)

Lembra-se da armadilha? Faça um fork do repositório e veja:

```bash
time rdc repo fork --parent my-app --tag test -m my-server
time rdc repo secret list --name my-app:test
```

**Vazio.**

O fork não tem chave Stripe. Nem palavra-passe de base de dados. Nem token de API. Os contentores no fork não conseguem interpolar `${REDIACC_SECRET_STRIPE_KEY}`. O ficheiro em `/var/run/rediacc/secrets/<fork-id>/STRIPE_KEY` não existe.

O fork não consegue fazer-se passar por si.

Se quiser segredos no fork para testes, defina-os explicitamente no fork -- valores de sandbox:

```bash
time rdc repo secret set --name my-app:test --key STRIPE_KEY --value sk_sandbox_yyy --mode file --current ""
```

Agora o fork fala com o sandbox do Stripe. As credenciais de produção nunca saíram da produção.

## Resumo

- `rdc repo secret` coloca as suas credenciais fora da imagem do repositório.
- O fork não consegue aceder-lhes.
- `get` devolve um digest, nunca o valor.
- Faça rotação quando esquecer. Não espie.

Segredos que o fork não consegue seguir.

---

Próximo: [Rede e Domínios](/pt/docs/tutorial-networking).
