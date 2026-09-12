# Домены
В исходном deploy.sh указаны gpz5.ru и www.gpz5.ru. Это найденная конфигурация, а не подтверждение текущего владения или DNS. PRIMARY_DOMAIN должен содержать один основной host без схемы; для production обычно gpz5.ru, если владелец подтвердит.

Пример .env:
```dotenv
PRIMARY_DOMAIN=gpz5.ru
ADDITIONAL_DOMAINS=www.gpz5.ru
SITE_DOMAINS=gpz5.ru,www.gpz5.ru
DJANGO_DEBUG=False
TRUST_PROXY=True
```
Caddy принимает указанные SITE_DOMAINS, автоматически получает HTTPS-сертификаты. Django разрешает PRIMARY_DOMAIN/ADDITIONAL_DOMAINS и перенаправляет алиасы на основной host с сохранением пути/query. Canonical, OpenGraph и sitemap используют основной host.

DNS у провайдера:
| Имя | Тип | Значение |
|---|---|---|
| @ основного домена | A | <PUBLIC_SERVER_IPV4> |
| @ основного домена | AAAA | <PUBLIC_SERVER_IPV6>, только если IPv6 настроен |
| www | CNAME | gpz5.ru. |
| дополнительные домены | A/AAAA | тот же фактический адрес сервера |

Не создавайте AAAA при отсутствии рабочего IPv6. IP сервера не предоставлен, поэтому не выдуман. Разрешите inbound 80/443, направьте записи до запроса сертификатов. Для Search Console и Яндекс Вебмастера TXT берётся из кабинета владельца (например google-site-verification=<TOKEN>); нельзя придумать токен. Добавьте sitemap.xml после проверки HTTPS и 301.

Проверки: curl -I https://gpz5.ru/; curl -I 'https://www.gpz5.ru/search/?q=7212'. Алиас должен вести к тому же пути на primary. HTTP → HTTPS → primary в Caddy может давать два перехода для HTTP-алиаса; при необходимости задайте явный redirect HTTP-алиасов на HTTPS primary в Caddy.
