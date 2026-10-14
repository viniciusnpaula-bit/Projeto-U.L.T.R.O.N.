# ULTRON Mobile — arquitetura interna (Etapa de contratos)

## Decisões de produto
- A IA principal é acessada pela internet.
- Funções básicas locais devem funcionar sem internet e sem o PC ligado.
- O ULTRON Core do Windows é opcional e não pode ser dependência de inicialização, conversa ou armazenamento.
- Não colocar chaves de API no código-fonte, no histórico Git ou no APK. Preferir um serviço intermediário que proteja as credenciais do provedor.
- Nenhuma saída da IA autoriza ações. Toda ação deve passar pelo gateway de segurança e pela política local.

## Estado e fluxo de aplicação
- `ConversationEngine` valida a entrada, tenta comandos locais primeiro e só então considera IA online.
- Intenções locais do tipo `ActionIntent` são encaminhadas ao `ActionGateway` injetado; não são executadas pelo provedor de IA.
- Se o gateway não estiver configurado, o motor falha fechado e retorna `ActionResult.Blocked`; não chama a IA como fallback para a intenção de ação.
- `ConversationReply.actionResult` permite à camada de interface representar sucesso, falha, bloqueio ou pedido de confirmação.
- O identificador da solicitação é imposto pela camada de conversa, não aceito do roteador local.
- O executor concreto deve permanecer privado na composição da aplicação e nunca ser exposto à UI ou ao provedor.

## Limites desta etapa
Esta alteração conecta o contrato do motor ao gateway, mas ainda não liga a UI real, não implementa ações do dispositivo, não conecta o provedor de rede e não adiciona segredos. A próxima etapa deve criar a composição segura do aplicativo e a UI de confirmação, com testes de ponta a ponta antes de habilitar ações reais.
