<!-- @format -->

# PUBobot2

**PUBobot2** is a Discord bot for pickup games organization. PUBobot2 has a remarkable list of features such as rating matches, rank roles, drafts, map vote polls, and more!

### Some screenshots

![screenshots](https://cdn.discordapp.com/attachments/824935426228748298/836978698321395712/screenshots.png)

### Using the public bot instance

If you want to test the bot, feel free to join [**Pubobot2-dev** Discord server](https://discord.gg/rjNt9nC).  
All the bot settings can be found and configured on the [Web interface](https://pubobot.leshaka.xyz/).  
For the complete list of commands see [COMMANDS.md](https://github.com/Leshaka/PUBobot2/blob/main/COMMANDS.md).  
You can invite the bot to your Discord server from the [web interface](https://pubobot.leshaka.xyz/) or use the direct [invite link](https://discord.com/oauth2/authorize?client_id=177021948935667713&scope=bot).

---

### Improvements and new phase flow

PUBobot2 now separates **ready check** and **map vote** into two distinct phases to improve match quality and prevent Elo manipulation:

- **READY_CHECK phase** → players confirm participation.
- **MAP_VOTE phase** → players vote for maps only after all have checked in.

This change helps reduce dodging behavior during the ready check and improves fairness in ranked games.

---

### Support

Hosting the service for everyone is not free, not to mention the actual time and effort to develop the project.  
If you enjoy the bot, please subscribe on [Boosty](https://boosty.to/leshaka).

---

## Hosting the bot yourself

### Requirements

- **Python 3.9+**
- **MySQL**
- **gettext** (for multilanguage support)

---

### Installing

1. Create MySQL user and database for PUBobot2:

   ```sql
   sudo mysql
   CREATE USER 'pubobot'@'localhost' IDENTIFIED BY 'your-password';
   CREATE DATABASE pubodb CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
   GRANT ALL PRIVILEGES ON pubodb.* TO 'pubobot'@'localhost';
   ```

2. Install required modules and configure PUBobot2:

   ```bash
   git clone https://github.com/Leshaka/PUBobot2
   cd PUBobot2
   pip3 install -r requirements.txt
   cp config.example.cfg config.cfg
   ```

3. Edit the config:

   ```bash
   nano config.cfg
   ```

   → Fill in your Discord bot token, MySQL credentials, and save.

4. (Optional) Compile translations:

   ```bash
   ./compile_locales.sh
   ```

5. Start the bot:
   ```bash
   python3 PUBobot2.py
   ```

If everything is installed correctly, the bot should launch without any errors and give you a CLI.

---

## Credits

Developer: **Leshaka**  
Contact: leshkajm@ya.ru

Used libraries:

- [discord.py](https://github.com/Rapptz/discord.py)
- [aiomysql](https://github.com/aio-libs/aiomysql)
- [emoji](https://github.com/carpedm20/emoji/)
- [glicko2](https://github.com/deepy/glicko2)
- [TrueSkill](https://trueskill.org/)
- [prettytable](https://github.com/jazzband/prettytable)

---

## License

Copyright (C) 2020 **Leshaka**

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License version 3 as published by the Free Software Foundation.

This program is distributed in the hope that it will be useful,  
but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  
See the GNU General Public License for more details.

See `'GNU GPLv3.txt'` for the full license text.

## Configuration Commands

The bot supports configuration through slash commands. These commands are only available to users with Admin or Moderator roles.

### Channel Configuration

- `/set-channel-config` - Update channel configuration using JSON
  - `config`: JSON configuration string
  - Example:
    ```json
    {
    	"prefix": "!",
    	"lang": "en",
    	"admin_role": "Admin",
    	"moderator_role": "Moderator",
    	"ranks": {
    		"bronze": 0,
    		"silver": 1000,
    		"gold": 2000,
    		"platinum": 3000,
    		"diamond": 4000
    	}
    }
    ```

### Queue Configuration

- `/set-queue-config` - Update queue configuration using JSON
  - `queue`: Name of the queue to configure
  - `config`: JSON configuration string
  - Example:
    ```json
    {
    	"min_players": 4,
    	"max_players": 10,
    	"rating_system": "glicko2",
    	"maps": ["map1", "map2", "map3"]
    }
    ```

### View Configuration

- `/view-config` - View current channel or queue configuration
  - `queue`: (Optional) Name of the queue to view config
