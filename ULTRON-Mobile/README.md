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

## Segurança
- Não inclua chaves da Groq no APK nem no repositório.
- As ações são apenas contratos nesta etapa; não há execução de ações externas implementada.
- Níveis de risco são definidos no código, não pela IA.
- Não configure credenciais reais até o backend seguro ser implementado.

## GitHub Actions
Workflow em `.github/workflows/android.yml`. Ele configura JDK 17, Android SDK e Gradle 8.9, executa testes e gera o APK de debug.
