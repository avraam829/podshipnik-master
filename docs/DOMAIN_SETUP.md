# Домены
В исходном deploy.sh указаны gpz5.ru и www.gpz5.ru. Это найденная конфигурация, а не подтверждение текущего владения или DNS. PRIMARY_DOMAIN должен содержать один основной host без схемы; для production обычно gpz5.ru, если владелец подтвердит.

Пример .env:
```dotenv
PRIMARY_DOMAIN=gpz5.ru
ADDITIONAL_DOMAINS=www.gpz5.ru,lyhgbearing.ru,lyc-bearing.ru,hrbbrg.ru,zys-bearings.ru,lycbearings.ru,skfcn.ru
SITE_DOMAINS=gpz5.ru, www.gpz5.ru, lyhgbearing.ru, lyc-bearing.ru, hrbbrg.ru, zys-bearings.ru, lycbearings.ru, skfcn.ru
DJANGO_DEBUG=False
TRUST_PROXY=True
```
Caddy принимает указанные SITE_DOMAINS, автоматически получает HTTPS-сертификаты. Django разрешает PRIMARY_DOMAIN/ADDITIONAL_DOMAINS и перенаправляет алиасы на основной host с сохранением пути/query. Canonical, OpenGraph и sitemap используют основной host.

Для действующего сервера после получения новой версии кода:

```bash
cd /opt/sba
python3 scripts/configure_domains.py
docker compose --profile production run --rm --no-deps proxy caddy adapt --config /etc/caddy/Caddyfile --adapter caddyfile > /dev/null
docker compose --profile production up -d --build --wait
docker compose logs --tail=100 proxy
```

Скрипт сохраняет резервную копию `.env`, обновляет три настройки доменов,
сохраняет остальные параметры и ранее добавленные алиасы. Секреты не выводятся.
Важно пересоздать также proxy: `docker compose restart` не обновляет его
переменные окружения. Дополнительные домены возвращают 301 на gpz5.ru.
`www` для новых доменов не добавлен: для него нужны отдельные DNS-записи.

DNS у провайдера:
| Имя | Тип | Значение |
|---|---|---|
| @ основного домена | A | <PUBLIC_SERVER_IPV4> |
| @ основного домена | AAAA | <PUBLIC_SERVER_IPV6>, только если IPv6 настроен |
| www | CNAME | gpz5.ru. |
| дополнительные домены | A/AAAA | тот же фактический адрес сервера |

Не создавайте AAAA при отсутствии рабочего IPv6. IP сервера не предоставлен, поэтому не выдуман. Разрешите inbound 80/443, направьте записи до запроса сертификатов. Для Search Console и Яндекс Вебмастера TXT берётся из кабинета владельца (например google-site-verification=<TOKEN>); нельзя придумать токен. Добавьте sitemap.xml после проверки HTTPS и 301.

Проверки: curl -I https://gpz5.ru/; curl -I 'https://www.gpz5.ru/search/?q=7212'. Алиас должен вести к тому же пути на primary. HTTP → HTTPS → primary в Caddy может давать два перехода для HTTP-алиаса; при необходимости задайте явный redirect HTTP-алиасов на HTTPS primary в Caddy.
