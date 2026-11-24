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
| `sensor.<name>_nursery_timeline` | Number of entries today; full timeline in the `entries` attribute |
| `sensor.<name>_nursery_latest_entry` | Most recent diary entry |
| `sensor.<name>_nursery_checked_in` | Check-in time |
| `sensor.<name>_nursery_last_nappy` | Last nappy change (with wet/soiled counts) |
| `sensor.<name>_nursery_nappy_changes` | Nappy changes today |
| `sensor.<name>_nursery_sleep_today` | Total sleep today (minutes) |
| `sensor.<name>_nursery_water_today` | Water today (mL) |
| `sensor.<name>_nursery_last_meal_eaten` | % of the last meal eaten |
| `image.<name>_nursery_latest_photo` | Latest diary photo |

The diary is polled every 15 minutes between 07:00 and 19:00.

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
