# LumiFlex CGM for Home Assistant

Пользовательская интеграция Home Assistant для получения данных из LumiFlex CGM https://cloud.lumiflex.ru/login и отображения их в Home Assistant.

Интеграция подключается к аккаунту LumiFlex, получает актуальные данные мониторинга глюкозы и обновляет сущности Home Assistant через `DataUpdateCoordinator`. Дополнительно поддерживается отправка последнего валидного значения глюкозы в Nightscout.

## Возможности

* Подключение к LumiFlex CGM через логин и пароль.
* Настройка интеграции через UI Home Assistant.
* Автоматическая проверка учётных данных при первичной настройке.
* Повторная настройка учётных данных через reconfigure flow.
* Настраиваемый интервал обновления данных.
* Поддержка Options Flow для изменения параметров без ручного редактирования YAML.
* Опциональная интеграция с Nightscout.
* Проверка корректности пары Nightscout URL + API Secret.
* Защита от повторной загрузки одного и того же значения в Nightscout.
* Сохранение последнего загруженного timestamp между перезапусками Home Assistant.
* Обработка ошибок авторизации и ошибок получения данных через стандартные механизмы Home Assistant.

## Что делает интеграция

LumiFlex CGM integration получает текущие данные из LumiFlex API и передаёт их в Home Assistant.
Если настроен Nightscout, интеграция дополнительно формирует запись в формате Nightscout и отправляет последнее валидное значение глюкозы.

Чтобы избежать дублей, интеграция сохраняет timestamp последней успешно отправленной записи и не загружает одно и то же значение повторно после перезапуска Home Assistant.

## Установка

### Ручная установка

1. Скопируйте папку интеграции в директорию:

```text
/config/custom_components/lumiflex/
```

2. Перезапустите Home Assistant.

3. Перейдите в:

```text
Settings → Devices & services → Add integration
```

4. Найдите интеграцию `LumiFlex CGM`.

5. Введите данные аккаунта LumiFlex и параметры обновления.

## Настройка

При добавлении интеграции нужно указать:

| Параметр              | Описание                                         |
| --------------------- | ------------------------------------------------ |
| Username              | Логин от аккаунта LumiFlex                       |
| Password              | Пароль от аккаунта LumiFlex                      |
| Update interval       | Интервал обновления данных в минутах             |
| Nightscout URL        | Адрес Nightscout, если требуется отправка данных |
| Nightscout API Secret | API Secret для Nightscout                        |

Nightscout является опциональным.
Если указывается `Nightscout URL`, необходимо также указать `Nightscout API Secret`. Если указан только один из этих параметров, интеграция покажет ошибку настройки.

## Изменение настроек

После добавления интеграции параметры можно изменить через настройки интеграции в Home Assistant.

Через Options Flow доступны:

* интервал обновления данных;
* Nightscout URL;
* Nightscout API Secret.

Учётные данные LumiFlex можно изменить через reconfigure flow.

## Nightscout

Интеграция может отправлять последнее валидное значение глюкозы в Nightscout.

Возможные статусы Nightscout:

| Статус              | Значение                                     |
| ------------------- | -------------------------------------------- |
| `disabled`          | Nightscout не настроен                       |
| `not_uploaded_yet`  | Nightscout настроен, но загрузки ещё не было |
| `uploaded`          | Последняя запись успешно отправлена          |
| `duplicate_skipped` | Запись уже была отправлена ранее и пропущена |
| `no_valid_entry`    | Нет валидной пары глюкоза/время для отправки |
| `upload_error`      | Ошибка при отправке данных в Nightscout      |

Интеграция сохраняет последний успешно загруженный timestamp в Home Assistant storage, чтобы не отправлять дубли после перезапуска системы.

## Обработка ошибок

Интеграция использует стандартные механизмы Home Assistant:

* при ошибке авторизации создаётся `ConfigEntryAuthFailed`;
* при ошибке получения данных создаётся `UpdateFailed`;
* ошибки LumiFlex API и Nightscout API обрабатываются отдельно;
* статус и текст ошибки Nightscout добавляются в данные координатора.

## Требования

* Home Assistant с поддержкой custom integrations.
* Аккаунт LumiFlex.
* Доступ к LumiFlex API.
* Nightscout — опционально.

## Disclaimer

This project is an unofficial Home Assistant custom integration for LumiFlex CGM.
It is not affiliated with, endorsed by, or officially supported by LumiFlex, Home Assistant, or Nightscout.

Use it at your own risk. This integration is intended for informational and automation purposes only and must not be used as a medical decision-making tool.
