# Mongobate

A Python-based application for managing chat interactions, music playback, and event handling with MongoDB integration. This project provides a flexible framework for handling various chat-based events, managing music queues, and triggering custom actions.

## Features

### Core Components

- **Event Handler**: Processes and manages various chat events and user interactions
- **Database Handler**: Manages MongoDB connections and data operations
- **Chat DJ**: Integrates with Spotify for music playback and queue management
- **Audio Player**: Handles audio playback for various events and actions

### Key Features

- **Spotify Integration**
  - Song request handling and queue management
  - Market availability checking
  - Playback device selection
  - Queue status monitoring
  
- **VIP System**
  - Custom audio triggers for VIP users
  - Cooldown management for audio triggers
  - User-specific audio file management
  
- **Command System**
  - Custom command parsing and handling
  - Admin command support
  - Configurable command symbols
  
- **OBS Integration**
  - Dynamic overlay management
  - Scene switching capabilities
  
- **Custom Actions**
  - User-specific action triggers
  - Custom audio responses
  - Configurable action messages

## Prerequisites

- Python 3.x
- MongoDB
- Elasticsearch (optional, for advanced logging)
- Spotify Developer Account (for music features)
- OpenAI API Key (for song extraction)

## Installation

1. Clone the repository:

```bash
git clone https://github.com/yourusername/mongobate.git
cd mongobate
```

2. Install required dependencies:

```bash
pip install -r requirements.txt
```

3. Create and configure `config.ini`:

```ini
[MongoDB]
username = your_username
password = your_password
host = localhost
port = 27017
db = your_database
collection = your_collection
aws_key = 
aws_secret = 

[Spotify]
client_id = your_spotify_client_id
client_secret = your_spotify_client_secret
redirect_url = your_redirect_url

[OpenAI]
api_key = your_openai_api_key

[Logging]
log_file = logs/mongobate.log
log_max_size_mb = 10
log_backup_count = 5

[Components]
chat_auto_dj = true
vip_audio = true
command_parser = true
custom_actions = true
spray_bottle = false
couch_buzzer = false
obs_integration = false
event_audio = true

[General]
song_cost = 100
skip_song_cost = 50
command_symbol = !
spray_bottle_cost = 25
vip_refresh_interval = 300
admin_refresh_interval = 300
vip_audio_cooldown_hours = 1
vip_audio_directory = audio/vip
```

## Usage

### Basic Setup

1. Start the application with database handler:

```bash
python app_and_db.py
```

2. Start the application and database handler separately:

```bash
python db.py
python app.py
```

### Component Configuration

Enable or disable components in the `config.ini` file under the `[Components]` section:

- `chat_auto_dj`: Enables Spotify integration and music requests
- `vip_audio`: Enables VIP user audio triggers
- `command_parser`: Enables custom command handling
- `custom_actions`: Enables user-specific action triggers
- `obs_integration`: Enables OBS scene control

### Audio Setup

1. Place VIP audio files in the configured `vip_audio_directory`
2. Configure VIP users and their associated audio files in the database
3. Set appropriate cooldown periods in the configuration

### Command System

Use the configured command symbol (default: !) to trigger commands:

- `!WTFU`: Trigger couch buzzer
- `!BRB`: Switch to BRB scene
- `!LIVE`: Switch to main scene

### Logging System

The application uses a comprehensive logging system with multiple outputs:

#### File Logging

- Rotating file logs with configurable size and backup count
- Separate log files for different components
- Automatic log directory creation
- UTF-8 encoding support

#### Console Logging

- Real-time console output
- Formatted messages with timestamp, component name, and log level
- Color-coded log levels (when supported)

#### Elasticsearch Integration

- Asynchronous logging to Elasticsearch
- Daily indices with automatic rotation (format: mongobate-YYYY.MM.DD)
- Bulk indexing for improved performance
- Secure authentication using API keys
- Detailed log documents including:
  - Timestamp
  - Host information
  - Log level
  - Component name
  - File path and line number
  - Function name
  - Exception details (when applicable)
  - Custom fields support

#### Configuration

```ini
[Logging]
log_file = logs/debug.log
log_file_db = logs/db.log
log_file_app = logs/app.log
log_max_size_mb = 10
log_backup_count = 10
elasticsearch_enabled = true

[Elasticsearch]
host = your-elasticsearch-host
port = 9200
index_prefix = mongobate
use_ssl = false
api_key = your-api-key-here
```

#### Features

- Centralized logging configuration
- Component-specific loggers
- Asynchronous Elasticsearch logging with batching
- Graceful shutdown and cleanup
- Error handling and automatic reconnection
- Queue-based logging to prevent blocking
- Support for structured logging with extra fields

## Development

### Project Structure

```
mongobate/
├── app.py                 # Main application entry point
├── app_and_db.py         # Application with database handler
├── handlers/             # Core handlers
│   ├── dbhandler.py     # Database operations
│   ├── eventhandler.py  # Event processing
│   └── obshandler.py    # OBS integration
├── helpers/             # Helper modules
│   ├── actions.py       # Action processing
│   ├── checks.py        # Validation functions
│   └── eventprocessor.py # Event processing logic
├── chatdj/             # Spotify integration
│   └── chatdj.py       # Auto DJ implementation
├── chataudio/          # Audio handling
│   └── audioplayer.py  # Audio playback
└── utils/              # Utility functions
    ├── config.py       # Configuration management
    ├── elastic.py      # Elasticsearch logging handler
    ├── logging_config.py # Centralized logging configuration
    └── jsonencoders.py # JSON encoding utilities
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## Known Issues

- When starting playback of first song to be added to queue, an error may occur but doesn't affect functionality

## TODO

- Add private message alert system
