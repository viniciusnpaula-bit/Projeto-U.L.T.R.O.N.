# ULTRON Mobile — arquitetura interna (Etapa de contratos)

## Decisões de produto
- A IA principal é acessada pela internet.
- Funções básicas locais devem funcionar sem internet e sem o PC ligado.
- O ULTRON Core do Windows é opcional e não pode ser dependência de inicialização, conversa ou armazenamento.
- Não colocar chaves de API no código-fonte, no histórico Git ou no APK. Preferir um serviço intermediário que proteja as credenciais do provedor.
- Nenhuma saída da IA autoriza ações. Toda ação deve passar pelo gateway de segurança e pela política local.

## Auditoria do estado atual

### O que já existe
- `MainActivity.kt`: tela Jetpack Compose, ainda com estados locais de demonstração e cartões que informam que os módulos estão em construção.
- `core/ai/AIProvider.kt`: interface mínima para geração de texto; ainda não há provedor de rede nem contrato de timeout/estado offline.
- `core/memory/MemoryStore.kt`: interface de busca, gravação e exclusão; não há implementação persistente nem operação explícita de limpar tudo.
- `core/security/ActionGateway.kt`, `ActionPolicyRegistry.kt`, `RiskLevel.kt` e confirmação/autenticação: base de política, allowlist, autenticação do proprietário, confirmação de uso único e auditoria.
- `core/actions/ActionExecutor.kt` e `SecureActionExecutor.kt`: contrato de execução e uma segunda abstração protegida que ainda precisa ser consolidada com `ActionGateway`.
- Testes existentes concentram-se na segurança.

### Lacunas e riscos a resolver antes de conectar uma IA real
1. A interface está concentrada em `MainActivity`; falta um ViewModel/orquestrador de conversa injetável.
2. `AIProvider` recebe texto e contexto como strings e não define limite de contexto, cancelamento, timeout ou proveniência da resposta.
3. `MemoryStore` não define política de retenção, limpeza completa ou implementação local persistente.
4. `ActionGateway` e `SecureActionExecutor` implementam verificações de segurança distintas e não devem ser encadeados cegamente: ambos exigem confirmação para ações HIGH, o que pode bloquear execuções legítimas ou criar fluxos de confirmação duplicados. A arquitetura da aplicação deve usar `ActionGateway` como único ponto de entrada da UI/IA e manter um executor de baixo nível privado atrás dele. `SecureActionExecutor` permanece legado/alternativo até uma revisão específica de remoção ou adaptação; não o injetar como executor interno do gateway.
5. `ActionGateway` recebe `ActionExecutor` no construtor. A composição deve manter a implementação concreta de baixo nível privada e não expor executor direto à UI ou ao provedor de IA. A aprovação interativa deve ocorrer no callback do gateway e a sessão do proprietário precisa continuar válida após a aprovação.
6. O manifesto ainda não declara permissão de internet; ela só deve ser adicionada quando o cliente online for implementado.
7. Não há detector de conectividade, roteador de comandos locais nem integração real de IA.
8. Os contratos de autenticação/biometria ainda precisam ser conectados a telas e fluxos reais; não presumir que a interface visual atual já protege ações.

## Contratos adicionados nesta etapa

- `core/conversation/ConversationContracts.kt`: mensagens tipadas, pedido de conversa, resposta com origem explícita, estado de conectividade, falhas normalizadas e interface `ConversationEngine`.
- `core/conversation/LocalCommandRouter.kt`: separa comandos locais seguros de pedidos que precisam da IA. Um resultado `ActionIntent` descreve uma ação, mas não a executa.

## Fluxo alvo

1. A interface envia `ConversationRequest` ao `ConversationEngine`.
2. O motor valida entrada e tenta `LocalCommandRouter` primeiro.
3. Se for uma resposta local, retorna `ReplyOrigin.LOCAL_COMMAND`; se for uma intenção de ação, encaminha-a exclusivamente ao `ActionGateway`.
4. Se não for comando local e houver rede, chama o `AIProvider` configurado e retorna `ReplyOrigin.ONLINE_AI`.
5. Sem rede, retorna um aviso local claro; funções locais continuam disponíveis. Não simular resposta da IA.
6. Histórico e memória são opcionais, locais e limitados. Segredos e argumentos sensíveis não entram em prompts nem logs.

## Etapa 2 — auditoria e reforço do gateway
- `ActionGateway` é o ponto de entrada pretendido para ações solicitadas pela UI ou pela IA.
- A implementação concreta de `ActionExecutor` deve permanecer privada na composição da aplicação; nunca deve ser entregue à UI ou ao provedor de IA.
- Não encadear `SecureActionExecutor` dentro de `ActionGateway` sem uma refatoração explícita: ambos aplicam políticas/confirmações e isso pode duplicar a confirmação.
- Testes devem cobrir allowlist, negação CRITICAL/irreversível, confirmação explícita, desafio de uso único, vinculação aos argumentos originais e expiração da sessão do proprietário durante a confirmação.
- O motor de conversa ainda não despacha `ActionIntent`; isso é deliberado até que uma camada de aplicação conecte intents exclusivamente ao gateway e modele corretamente o estado de confirmação.

## Próxima implementação
1. Integrar uma camada de aplicação/ViewModel que despache `ActionIntent` exclusivamente ao `ActionGateway`, incluindo o estado de confirmação.
2. Testar o fluxo completo de ação com gateway falso e verificar que não existe execução direta pelo motor de conversa.
3. Só depois integrar o provedor online via camada de rede, sem segredo embutido no aplicativo.

## Limites desta entrega
Esta alteração define contratos e registra auditoria. Não adiciona chamadas de rede, comandos reais, persistência, permissões extras nem integração com o PC.
