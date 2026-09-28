import yandex_music

print("Track methods with download:")
print([m for m in dir(yandex_music.Track) if "download" in m])

print("\nDownloadInfo methods:")
print([m for m in dir(yandex_music.DownloadInfo) if not m.startswith("_")])
