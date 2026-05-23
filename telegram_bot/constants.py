class EventType:
    REGISTRATION = 0
    SEARCH = 1
    DOWNLOAD = 2
    ADD_TO_FAVORITES = 3
    DOWNLOAD_PLAYLIST = 4
    SHOW_AD = 5

    CHOICES = (
        (REGISTRATION, 'Регистрация'),
        (SEARCH, 'Поиск трека'),
        (DOWNLOAD, 'Скачивание трека'),
        (ADD_TO_FAVORITES, 'Добавление в избранное'),
        (DOWNLOAD_PLAYLIST, 'Скачивание подборки'),
        (SHOW_AD, 'Показ рекламы'),
    )

    NAMES = {
        REGISTRATION: 'Регистрация',
        SEARCH: 'Поиск трека',
        DOWNLOAD: 'Скачивание трека',
        ADD_TO_FAVORITES: 'Добавление в избранное',
        DOWNLOAD_PLAYLIST: 'Скачивание подборки',
        SHOW_AD: 'Показ рекламы',
    }

MAX_TG_UPLOAD = 48 * 1024 * 1024
