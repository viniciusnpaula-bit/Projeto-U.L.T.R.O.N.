# ULTRON Mobile

Aplicativo Android nativo para uso pessoal, com interface em português, foco em segurança e arquitetura extensível.

## Estado desta entrega
**Scaffold inicial (Etapa 1).** Inclui projeto Gradle, tela inicial Compose, contratos centrais de IA/memória/segurança/execução, matriz de risco inicial, testes unitários e pipeline GitHub Actions. Ainda não inclui integração real com Groq, banco Room, voz contínua ou automações avançadas.

## Requisitos
- JDK 17
- Android SDK (compileSdk 35)
- O workflow do GitHub Actions instala Gradle 8.9 diretamente nesta etapa inicial. O Gradle Wrapper deve ser adicionado assim que o ambiente de desenvolvimento local estiver disponível, para builds reproduzíveis fora do CI.

## Abrir/compilar
No Android Studio: abra esta pasta e aguarde a sincronização do Gradle.
Pela linha de comando, após configurar Android SDK e gerar/validar o wrapper:
```bash
gradle wrapper --gradle-version 8.9
./gradlew testDebugUnitTest assembleDebug
```
No Windows:
```powershell
gradle wrapper --gradle-version 8.9
.\gradlew.bat testDebugUnitTest assembleDebug
```

APK de debug esperado:
`app/build/outputs/apk/debug/app-debug.apk`

## Segurança (hardening em andamento)
- `SecurityManager` decide a política; ações desconhecidas, críticas e irreversíveis são negadas.
- `SecureActionExecutor` é o gateway central para execução. Os executores de plataforma devem ficar encapsulados e não ser chamados diretamente pela UI/IA.
- Ações HIGH exigem sessão autenticada do proprietário e uma confirmação de uso único, vinculada ao ID da ação e aos argumentos, com expiração monotônica. Tokens pendentes ficam apenas em memória e desaparecem ao encerrar o processo.
- `AndroidOwnerAuthenticator` permite cadastrar PIN de 6+ dígitos. O PIN não é persistido; o verificador usa HMAC com chave não exportável no Android Keystore, com bloqueio progressivo após falhas. Não há PIN padrão.
- `BiometricOwnerGate` fornece autenticação biométrica forte opcional para uma `FragmentActivity`; o fluxo ainda precisa ser ligado a uma tela de configuração/confirmação.
- `SecurityAudit` registra metadados de autorização e bloqueio; não passe PIN, token, prompt ou argumentos sensíveis para o logger.
- A dependência AndroidX Biometric foi adicionada como preparação; a tela/fluxo de biometria ainda precisa ser conectado e testado no dispositivo.
- Não inclua chaves da Groq no APK nem no repositório. A integração de IA deve chamar um backend que mantém o segredo no servidor.
- Ainda não há ações reais de plataforma integradas nem fluxo de cadastro/login conectado à interface. Não trate este branch como versão pronta para uso.


## GitHub Actions
Workflow em `.github/workflows/android.yml`. Ele configura JDK 17, Android SDK e Gradle 8.9, executa testes e gera o APK de debug.
