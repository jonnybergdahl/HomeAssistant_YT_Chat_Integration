# YouTube Chat for Home Assistant

A custom Home Assistant integration that monitors YouTube Live Chat for commands and fires events when keywords are matched. Let your viewers control your smart home!

## Features

- Monitors your own or any other channel's live broadcast chat in real time
- Detects `!command parameter` messages (e.g., `!lights off`, `!color red`)
- Fires Home Assistant events for each matched command
- Creates a sensor per keyword showing the last received parameter
- Configurable role filtering (Everyone, Moderators and owner, Owner only)
- Supports multiple YouTube channels per Google account
- Dynamic polling interval based on YouTube API recommendations
- HACS compatible

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu in the top right and select **Custom repositories**
3. Add `https://github.com/jonnybergdahl/HomeAssistant_YT_Chat_Integration` as an **Integration**
4. Search for "YouTube Chat" and install it
5. Restart Home Assistant

### Manual

1. Copy the `custom_components/youtube_chat` folder into your Home Assistant `custom_components` directory
2. Restart Home Assistant

## Google Cloud Setup

Before configuring the integration, you need to set up a Google Cloud project:

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (or select an existing one)
3. Enable the **YouTube Data API v3**
4. Go to **APIs & Services > Credentials**
5. Create an **OAuth 2.0 Client ID** (Web Application type)
6. Add `https://<your-ha-instance>/auth/external/callback` as an authorized redirect URI
7. Note down the **Client ID** and **Client Secret**

## Configuration

1. In Home Assistant, go to **Settings > Devices & Services**
2. Click **Add Integration** and search for **YouTube Chat**
3. Before starting the flow, go to **Settings > Application Credentials** and add your Google Client ID and Client Secret
4. Follow the OAuth2 flow to authenticate with your Google account
5. If your account has multiple YouTube channels, select which one to use for authentication
6. Choose whether to monitor **your own channel** or **another channel's** live chat
7. If monitoring another channel, enter their channel ID (the `UCxxxxxxxx` value from their channel URL)

## Entities

For a channel named "MyChannel", the following entities are created:

| Entity | Type | Description |
|---|---|---|
| `binary_sensor.mychannel_yt_chat_is_live` | Binary Sensor | Whether the channel is currently live |
| `sensor.mychannel_yt_chat_viewer_count` | Sensor | Current viewer count (available only when live) |
| `text.mychannel_yt_chat_keywords` | Text | Comma-separated list of keywords to monitor |
| `select.mychannel_yt_chat_allowed_roles` | Select | Who can trigger commands |

### Keyword Sensors

For each keyword in the keywords list, a sensor is created dynamically:

| Entity | State | Attributes |
|---|---|---|
| `sensor.mychannel_yt_chat_keyword_lights` | Last parameter (e.g., `off`) | `author`, `message`, `matched_at` |
| `sensor.mychannel_yt_chat_keyword_color` | Last parameter (e.g., `red`) | `author`, `message`, `matched_at` |

Keyword sensors are created and removed automatically when you edit the keywords list — no restart needed. Their state persists across Home Assistant restarts.

## How Commands Work

The integration watches for chat messages matching the pattern `!command parameter`:

- `!lights off` — keyword: `lights`, parameter: `off`
- `!color red` — keyword: `color`, parameter: `red`
- `!scene party` — keyword: `scene`, parameter: `party`

If the keywords list is empty, all valid `!command parameter` messages pass through. If keywords are set (e.g., `lights,color,scene`), only those commands are matched.

## Events

Each matched command fires a `youtube_chat_keyword_detected` event:

```yaml
event_type: youtube_chat_keyword_detected
data:
  keyword: "lights"
  parameter: "off"
  author: "ViewerName"
  author_channel_id: "UCxxxxxxxx"
  message: "!lights off"
  matched_at: "2026-03-11T20:15:00+00:00"
```

## Automation Examples

### Trigger on a specific keyword

```yaml
automation:
  - alias: "YouTube Chat - Lights Control"
    trigger:
      - platform: event
        event_type: youtube_chat_keyword_detected
        event_data:
          keyword: "lights"
    action:
      - service: light.turn_{{ trigger.event.data.parameter }}
        target:
          entity_id: light.living_room
```

### Trigger on any keyword

```yaml
automation:
  - alias: "YouTube Chat - Log All Commands"
    trigger:
      - platform: event
        event_type: youtube_chat_keyword_detected
    action:
      - service: logbook.log
        data:
          name: "YouTube Chat"
          message: "{{ trigger.event.data.author }} used !{{ trigger.event.data.keyword }} {{ trigger.event.data.parameter }}"
```

### Use sensor state

```yaml
automation:
  - alias: "YouTube Chat - Color from Sensor"
    trigger:
      - platform: state
        entity_id: sensor.mychannel_yt_chat_keyword_color
    action:
      - service: light.turn_on
        target:
          entity_id: light.led_strip
        data:
          color_name: "{{ states('sensor.mychannel_yt_chat_keyword_color') }}"
```

## Monitoring Other Channels

You can monitor any public YouTube channel's live chat, not just your own. During setup, choose **Other channel** and enter the target channel's ID.

To find a channel ID:
1. Go to the channel's YouTube page
2. The channel ID is in the URL: `youtube.com/channel/UCxxxxxxxx`
3. Alternatively, you can find it via the channel's About page

When monitoring another channel, the integration uses the YouTube Search API to find their active live stream, then polls the chat as normal. Note that the Search API has a higher quota cost (100 units per call vs 1 for own broadcasts), so the integration checks for new broadcasts every 60 seconds when the channel is not live.

You can add the integration multiple times to monitor several channels simultaneously.

## Role Filtering

The **Allowed roles** select entity controls who can trigger commands:

| Option | Who can trigger |
|---|---|
| **Owner only** (default) | Only the channel owner |
| **Moderators and owner** | Channel moderators and the owner |
| **Everyone** | Any viewer |

Messages from users below the selected role are silently ignored.

## License

MIT License - see [LICENSE](LICENSE) for details.
