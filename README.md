# ParentAdmin Nursery Diary for Home Assistant

Unofficial Home Assistant integration for nurseries that use **ParentAdmin** (Nursery In a Box).
It reads your child's daily diary from the parent web portal and shows it in Home Assistant,
including a timeline card laid out like the ParentAdmin website, with photos.

> ParentAdmin has no public API. This integration logs in to the parent portal the same way a
> browser does and reads the diary page, so it may break if the site changes. Not affiliated with
> Nursery In a Box Ltd.

## Installation (HACS)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/YG98/ha-parentadmin`, type **Integration**.
2. Install **ParentAdmin Nursery Diary** and restart Home Assistant.
3. Settings → Devices & services → **Add integration** → *ParentAdmin Nursery Diary*, and log in with your
   ParentAdmin email and password.

## Entities

| Entity | Description |
|---|---|
| `sensor.<name>_nursery_timeline` | Number of diary entries; full timeline in the `entries` attribute, plus `date`, `is_today`, `booked_today` |
| `sensor.<name>_nursery_latest_entry` | Most recent diary entry (`datetime` attribute for "x ago" templates) |
| `sensor.<name>_nursery_checked_in` | Check-in time |
| `sensor.<name>_nursery_last_nappy` | Last nappy change (with wet/soiled counts) |
| `sensor.<name>_nursery_nappy_changes` | Nappy changes |
| `sensor.<name>_nursery_sleep_today` | Total sleep (minutes) |
| `sensor.<name>_nursery_water_today` | Water (mL) |
| `sensor.<name>_nursery_last_meal_eaten` | % of the last meal eaten |
| `sensor.<name>_nursery_unread_messages` | Unread inbox messages (latest five in `messages`) |
| `sensor.<name>_nursery_accident_and_incident_forms` | Number of accident / incident forms |
| `sensor.<name>_nursery_account_balance` | Account balance in GBP (negative = in debit), last payment as attributes |
| `sensor.<name>_nursery_latest_invoice` | Latest invoice total, with period, number and issue date |
| `sensor.<name>_nursery_booked_hours_today` | Today's booked hours, e.g. `09:00-17:00`, or `Not booked` / `Sick` / `Absent` / `Closed` |
| `binary_sensor.<name>_nursery_nursery_today` | On when booked in today |
| `binary_sensor.<name>_nursery_balance_owed` | On when the account is in debit |
| `image.<name>_nursery_latest_photo` | Latest diary photo |

The diary, inbox and incident forms are checked every 15 minutes between 07:00 and 19:00 (every
2 hours on days she isn't booked in). Invoices, the balance and the booking pattern are checked
every 3 hours. When today has no diary (weekends, holidays), the diary sensors and the card show
the most recent nursery day instead, with `is_today: false`.

## Events

| Event | When | Data |
|---|---|---|
| `parentadmin_new_invoice` | A new invoice appears | `number`, `period`, `issue_date`, `total`, `currency`, `balance` |
| `parentadmin_new_incident` | The accident / incident forms change and aren't empty | `count` |
| `parentadmin_new_message` | A new unread inbox message appears | `sender`, `subject`, `preview`, `received` |

Already-seen items are remembered across restarts, so you're only notified once.

```yaml
alias: Nursery - new invoice
triggers:
  - trigger: event
    event_type: parentadmin_new_invoice
actions:
  - action: notify.mobile_app_<your_phone>
    data:
      title: New nursery invoice
      message: "{{ trigger.event.data.period }}: £{{ '%.2f' | format(trigger.event.data.total) }}"
```

## Timeline card

The card is bundled with the integration and loads automatically (hard-refresh your browser after installing).

```yaml
type: custom:parentadmin-timeline-card
entity: sensor.<name>_nursery_timeline
title: Today at nursery   # optional
order: asc                # asc (like the website) or desc
photo_columns: 1          # 1 = full width like the website
show_header: true
```

Photos are fetched by Home Assistant and served through short-lived signed URLs, so they are never
publicly accessible.

## Troubleshooting

Enable debug logging from the integration's page, or check the logs for `custom_components.parentadmin`.
If the diary page changes, save it from your browser and run `python tools/test_parser.py saved-page.html`
to see what the parser makes of it.
