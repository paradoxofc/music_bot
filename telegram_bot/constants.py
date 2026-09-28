class EventType:
    REGISTRATION = 0
    SEARCH = 1
    DOWNLOAD = 2
    ADD_TO_FAVORITES = 3
    BROADCAST = 4
    SHOW_AD = 5

    CHOICES = (
        (REGISTRATION, 'Регистрация'),
        (SEARCH, 'Поиск трека'),
        (DOWNLOAD, 'Скачивание трека'),
        (ADD_TO_FAVORITES, 'Добавление в избранное'),
        (BROADCAST, 'Рассылка'),
        (SHOW_AD, 'Показ рекламы'),
    )

    NAMES = {
        REGISTRATION: 'Регистрация',
        SEARCH: 'Поиск трека',
        DOWNLOAD: 'Скачивание трека',
        ADD_TO_FAVORITES: 'Добавление в избранное',
        BROADCAST: 'Рассылка',
        SHOW_AD: 'Показ рекламы',
    }

MAX_TG_UPLOAD = 48 * 1024 * 1024
MIN_ALBUM_TRACKS = 4
