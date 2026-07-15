# ira_koh

## Git Relay

Механізм дистанційного виконання команд на сервері через сам git-репозиторій,
без прямого доступу до терміналу.

Як це працює:

1. На сервері (`/root/my-bot/`, WorkingDirectory юніта `cmdrunner.service`)
   постійно працює `cmd_runner.py` як systemd-сервіс (`Restart=always`).
2. Кожні 5 секунд він читає `cmds/pending.json` через GitHub Contents API
   (використовує `GITHUB_TOKEN` з оточення або з `.env`).
3. Якщо `id` у файлі відрізняється від останнього обробленого — команда з
   поля `cmd` виконується як shell-команда (`subprocess.run(..., shell=True)`)
   з таймаутом 120 секунд.
4. Результат пушиться назад у `cmds/result.json` через той самий GitHub API,
   після чого `id` запам'ятовується локально (файл `.cmd_runner_state`,
   не комітиться), щоб команда не виконалась повторно після рестарту сервісу.
5. Щоб надіслати нову команду — достатньо запушити оновлений
   `cmds/pending.json` у гілку `main` (наприклад, з боку Claude через
   GitHub API/MCP). Автодеплой (`/root/autodeploy.sh`, systemd-таймер,
   раз на хвилину `git pull`) синхронізує сам код `cmd_runner.py` та юніт,
   якщо вони змінюються.

### Формат `cmds/pending.json`

```json
{"id": "unique-id", "cmd": "shell command to run"}
```

### Формат `cmds/result.json`

```json
{
  "id": "unique-id",
  "cmd": "shell command that ran",
  "stdout": "останні 3000 символів stdout",
  "stderr": "stderr",
  "returncode": 0,
  "ts": "2026-07-15T12:00:00Z"
}
```

### ⚠️ Безпека

Це, по суті, канал віддаленого виконання команд від імені `root` без
додаткової автентифікації — доступ до нього дає **будь-хто, хто може
запушити в цей репозиторій або має чинний `GITHUB_TOKEN`**. Тримайте
репозиторій приватним, обмежуйте список колаборейторів і ротуйте токен,
якщо є підозра на витік.

### Встановлення юніта на сервері

```bash
cp cmdrunner.service /etc/systemd/system/cmdrunner.service
systemctl daemon-reload
systemctl enable --now cmdrunner.service
```