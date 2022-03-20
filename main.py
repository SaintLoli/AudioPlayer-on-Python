import sys
import os
import io
import random
import datetime
import stagger
import sqlite3

from eyed3 import id3, load
from PIL import Image, ImageFilter
from PyQt5 import uic
from PyQt5.QtWidgets import QApplication, QMainWindow, QTableWidgetItem, QFileDialog, \
    QInputDialog, QHeaderView
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import QTimer, QUrl


class DataBaseChecker:
    """Класс для работы с базой данных"""
    def __init__(self, window):
        self.con = sqlite3.connect('Database.sqlite')
        self.cur = self.con.cursor()
        self.window = window
        self.name = ''

    def check_artist(self, artist):
        """Есть ли исполнитель в базе"""
        if (artist,) not in self.cur.execute("SELECT artist FROM Artists").fetchall():
            self.cur.execute(f'INSERT INTO Artists(artist) VALUES("{artist}")')
            self.con.commit()

    def check_album(self, album):
        """Есть ли альбом в базе"""
        if (album,) not in self.cur.execute("SELECT album FROM Albums").fetchall():
            self.cur.execute(f'INSERT INTO Albums(album) VALUES("{album}")')
            self.con.commit()

    def check_track(self, track, artist, album, dur, path):
        """Есть ли трек в базе"""
        artist = self.cur.execute(f"""SELECT id FROM Artists
                                WHERE artist = '{artist}'""").fetchone()[0]
        album = self.cur.execute(f"""SELECT id FROM Albums
                                 WHERE album = '{album}'""").fetchone()[0]

        if (track, artist, album) not in self.cur.execute("""SELECT title, artist_id, album_id FROM Tracks"""):
            self.cur.execute(f'''INSERT INTO TRACKS(title, artist_id, album_id, duration, path)
                                VALUES("{track}", "{artist}", "{album}", "{dur}", "{path}")''')
            self.con.commit()
        elif path != self.cur.execute(f"""SELECT path FROM Tracks WHERE title = '{track}' 
                                        and artist_id = '{artist}'""").fetchone()[0]:
            self.cur.execute(f"""UPDATE Tracks
                                SET path = '{path}'
                                WHERE title = '{track}' and artist_id = '{artist}'""")
            self.con.commit()

    def add_playlist(self):
        """Добавлениие нового плейлиста в базу"""
        PlaylistDialog().new_playlist(self)
        if self.name:
            self.cur.execute(f'''INSERT INTO Playlists(title, track_list) VALUES("{self.name}", '{""}')''')
            self.con.commit()
            self.window.open_window_with_playlists()

    def get_playlists(self):
        return [i[0] for i in self.cur.execute("""SELECT title FROM Playlists""").fetchall()]

    def get_tracks_by_artist(self, artist):
        """Все треки по артисту"""
        global TRACKS
        self.name = artist
        paths = [i[0] for i in self.cur.execute(f"""SELECT path FROM Tracks
            WHERE artist_id IN (
            SELECT id FROM Artists
            WHERE artist = '{artist}')
        """).fetchall()]
        TRACKS.k = False
        TRACKS.set_playlist(paths)
        TRACKS.k = True

    def get_tracks_by_album(self, album):
        """Все треки в альбоме"""
        global TRACKS
        self.name = album
        paths = [i[0] for i in self.cur.execute(f"""SELECT path FROM Tracks
                    WHERE album_id IN (
                    SELECT id FROM Albums
                    WHERE album = '{album}')
                """).fetchall()]
        TRACKS.k = False
        TRACKS.set_playlist(paths)
        TRACKS.k = True

    def get_tracks_by_playlist(self, playlist):
        """Все треки в плейлисте"""
        global TRACKS
        self.name = playlist
        ids = tuple(eval(self.cur.execute(f"""SELECT track_list FROM Playlists 
                                        WHERE title = '{playlist}'""").fetchone()[0]))
        if ids != ():
            if len(ids) > 1:
                paths = [i[0] for i in self.cur.execute(f"""SELECT path FROM Tracks 
                                        WHERE id in {ids}""").fetchall()]
            elif len(ids) == 1:
                paths = [i[0] for i in self.cur.execute(f"""SELECT path FROM Tracks 
                                        WHERE id = {ids[0]}""").fetchall()]
            else:
                paths = 1
            TRACKS.k = False
            TRACKS.set_playlist(paths)
            TRACKS.k = True

    def add_track_in_playlist(self):
        """добавить трек в плейлист"""
        PlaylistDialog().add_track(self)
        if self.name != '':
            try:
                tracks_in_playlist_now = eval(self.cur.execute(f"""
                    SELECT track_list FROM Playlists WHERE title = '{self.name}'
                """).fetchone()[0])
            except SyntaxError:
                tracks_in_playlist_now = []

            id_pl = self.cur.execute(f"""SELECT id FROM Tracks 
            WHERE path = '{PLAYLIST.get_playlist()[AudioIndex].path()}'
            """).fetchone()[0]

            if id_pl not in tracks_in_playlist_now:
                tracks_in_playlist_now.append(id_pl)
                tracks_in_playlist_now.sort()

            self.cur.execute(f"""
            UPDATE Playlists
            SET track_list = '{tracks_in_playlist_now}'
            WHERE title = '{self.name}'
            """)
            self.con.commit()

    def remove_track(self):
        """Удалить из плейлиста"""
        global AudioIndex
        tracks_in_playlist_now = eval(self.cur.execute(f"""
                        SELECT track_list FROM Playlists WHERE title = '{self.name}'
                    """).fetchone()[0])

        id_pl = self.cur.execute(f"""SELECT id FROM Tracks 
                WHERE path = '{PLAYLIST.get_playlist()[AudioIndex].path()}'
                """).fetchone()[0]

        if id_pl in tracks_in_playlist_now:
            tracks_in_playlist_now.remove(id_pl)

        self.cur.execute(f"""
                UPDATE Playlists
                SET track_list = '{tracks_in_playlist_now}'
                WHERE title = '{self.name}'
                """)
        self.con.commit()
        self.get_tracks_by_playlist(self.name)
        if AudioIndex != 0:
            AudioIndex -= 1

        if len(PLAYLIST.get_playlist()) > 1:
            PLAYLIST.set_playlist([i.path() for i in TRACKS.get_playlist()])
            self.window.set_table()
            self.window.set_audio()
            self.window.play_audio()
        else:
            AudioIndex = 0
            self.window.player.stop()
            self.window.play.setVisible(True)
            self.window.pause.setVisible(False)
            self.window.open_window_with_playlists()
            self.cur.execute(f"""
                            UPDATE Playlists
                            SET track_list = ''
                            WHERE title = '{self.name}'
                            """)
            self.con.commit()

    def remove_playlist(self):
        self.cur.execute(f'''DELETE FROM Playlists WHERE title = "{self.name}"''')
        self.con.commit()
        self.window.open_window_with_playlists()



class PlayerWindow(QMainWindow):
    def __init__(self, content, main_window=None):
        super().__init__()
        uic.loadUi('resources/interfaces/Player.ui', self).show()
        self.setWindowTitle('AudioPlayer by AVV')
        self.setWindowIcon(QIcon('icon.ico'))
        self.player = QMediaPlayer()
        self.player.setVolume(0)
        self.info = None
        self.main_win = main_window
        self.content = content
        self.back.clicked.connect(self.go_back)
        self.back.setIcon(QIcon('resources/pictures/buttons/back.png'))

        self.set_ui()

    def set_ui(self):
        """Открытие окна полноразмерного плеера"""
        if self.__class__.__name__ == 'PlayerWindow':
            _main = ''
        else:
            _main = '_main'

        self.play.clicked.connect(self.play_audio)
        self.play.setIcon(QIcon(f'resources/pictures/buttons/play{_main}.png'))

        self.pause.clicked.connect(self.pause_audio)
        self.pause.setIcon(QIcon(f'resources/pictures/buttons/pause{_main}.png'))

        self.next.clicked.connect(self.next_audio)
        self.next.setIcon(QIcon(f'resources/pictures/buttons/next{_main}.png'))

        self.previously.clicked.connect(self.prev_audio)
        self.previously.setIcon(QIcon(f'resources/pictures/buttons/prev{_main}.png'))

        self.Album_pic.setPixmap(QPixmap('resources/pictures/music_default.png'))

        self.set_audio()
        self.play_audio()

    def play_audio(self):
        self.pause.setVisible(True)
        self.play.setVisible(False)

        if AudioIndex == 0:
            self.previously.setVisible(False)
        else:
            self.previously.setVisible(True)

        if AudioIndex == len(PLAYLIST.get_playlist()) - 1:
            self.next.setVisible(False)
        else:
            self.next.setVisible(True)
        if self.__class__.__name__ == 'PlayerWindow':
            self.main_win.play_audio()
        self.player.play()

    def pause_audio(self):
        self.pause.setVisible(False)
        self.play.setVisible(True)
        if self.__class__.__name__ == 'PlayerWindow':
            self.main_win.pause_audio()
        self.player.pause()

    def next_audio(self):
        global AudioIndex
        #print('do --->', AudioIndex)
        try:
            if self.__class__.__name__ == 'MainWindow' or self.next.sender().__class__.__name__ == 'QPushButton':
                AudioIndex += 1

            #print('posle --->', AudioIndex)

            self.set_audio()
            if self.__class__.__name__ == 'PlayerWindow':
                self.main_win.set_audio()
            self.play_audio()
        except IndexError:
            pass

    def prev_audio(self):
        global AudioIndex
        if AudioIndex != 0 and self.__class__.__name__ == 'PlayerWindow':
            AudioIndex -= 1
            self.main_win.siren = True
            self.main_win.prev_audio()
            self.main_win.siren = False
        elif self.__class__.__name__ == 'MainWindow' and not self.siren and AudioIndex != 0:
            AudioIndex -= 1
        elif AudioIndex < 0:
            AudioIndex = 0

        self.set_audio()
        self.play_audio()

    def set_audio(self):
        """Установка играющего трека"""
        if self.__class__.__name__ == 'PlayerWindow':
            self.info = InformationAboutAudio(self, self.main_win.Duration.value())
        else:
            self.info = InformationAboutAudio(self, 0)
        self.content = QMediaContent(PLAYLIST.get_playlist()[AudioIndex])

        self.player.setMedia(self.content)

    def go_back(self):
        """Возврат на главный экран"""
        self.main_win.show()
        self.player.stop()
        self.close()


class MainWindow(PlayerWindow, QMainWindow):
    def __init__(self):
        super(QMainWindow, self).__init__()
        self.player = QMediaPlayer()
        self.siren = False
        self.tracks_in_main = TRACKS.get_playlist().copy()
        uic.loadUi('resources/interfaces/MainWindow.ui', self)
        self.setWindowTitle('AudioPlayer by AVV')
        self.setWindowIcon(QIcon('icon.ico'))

        self.Playlists.clicked.connect(self.open_window_with_playlists)
        self.Playlists.setIcon(QIcon('resources/pictures/buttons/playlist.png'))
        self.Main.clicked.connect(self.open_main_window)
        self.Main.setIcon(QIcon('resources/pictures/buttons/main.png'))
        self.Alb.clicked.connect(self.open_window_with_albums)
        self.Alb.setIcon(QIcon('resources/pictures/buttons/album.png'))
        self.Art.clicked.connect(self.open_window_with_artists)
        self.Art.setIcon(QIcon('resources/pictures/buttons/artist.png'))
        self.add_path.clicked.connect(self.add_path_to_txt)
        self.add_path.setIcon(QIcon('resources/pictures/buttons/add_folder.png'))
        self.shuffle.setIcon(QIcon('resources/pictures/buttons/shuffle.png'))
        self.shuffle.clicked.connect(self.shuffle_tracks)
        self.full_screen.clicked.connect(self.start_play_with_new_window)
        self.artist, self.album, self.playlist, self.main = False, False, False, False
        self.is_playlist = False

        self.base = DataBaseChecker(self)
        self.add.clicked.connect(self.base.add_playlist)
        self.add.setIcon(QIcon('resources/pictures/buttons/add_playlist.png'))
        self.add_in_playlist.clicked.connect(self.base.add_track_in_playlist)
        self.add_in_playlist.setIcon(QIcon('resources/pictures/buttons/add_playlist.png'))
        self.remove.clicked.connect(self.base.remove_track)
        self.remove.setIcon(QIcon('resources/pictures/buttons/delete.png'))
        self.remove.setVisible(False)
        self.remove_playlist.setIcon(QIcon('resources/pictures/buttons/delete.png'))
        self.remove_playlist.clicked.connect(self.base.remove_playlist)
        self.remove_playlist.setVisible(False)

        self.window = None
        self.set_ui()
        self.pause_audio()

        self.set_table()

    def set_table(self):
        """Вывод таблицы с треками"""
        global ARTISTS, ALBUMS
        try:
            self.add.setVisible(False)
            self.shuffle.setVisible(True)

            self.files.setRowCount(len(TRACKS.get_playlist()))
            self.files.setColumnCount(4)

            for row, audio in enumerate(TRACKS.get_playlist()):
                tag = id3.Tag()
                tag.parse(audio.path())
                file = load(audio.path())

                title = tag.title if tag.title else audio.path().split('/')[-1]
                artist = tag.artist if tag.artist else 'Неизв. исполнитель'
                ARTISTS.add(artist)
                album = tag.album if tag.album else 'Неизв. альбом'
                ALBUMS.add(album)
                time = int(file.info.time_secs)

                self.base.check_artist(artist)
                self.base.check_album(album)
                self.base.check_track(title, artist, album, time, audio.path())

                self.files.setItem(row, 0, QTableWidgetItem(title))
                self.files.setItem(row, 1, QTableWidgetItem(artist))
                self.files.setItem(row, 2, QTableWidgetItem(album))
                self.files.setItem(row, 3, QTableWidgetItem(str(
                    datetime.time(minute=time // 60, second=time % 60).strftime('%M:%S'))
                ))

                self.set_size()

            self.files.setGeometry(40, 60, 613, 461)
            self.connecting()
        except FileNotFoundError:
            self.open_main_window()

    def set_size(self, res=False):
        """Размер таблицы"""
        if not res:
            self.files.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            self.files.verticalHeader().setDefaultSectionSize(45)
            self.files.horizontalHeader().setDefaultSectionSize(400)
            self.files.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        else:
            self.files.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            self.files.verticalHeader().setDefaultSectionSize(45)
            self.files.horizontalHeader().setDefaultSectionSize(613)

    def start_play_with_new_window(self):
        """Открыть полноразмерный плеер"""
        self.window = PlayerWindow(self.content, self)
        self.window.show()
        self.hide()

    def start_play(self, row):
        """добавление трека из таблицы в играющее"""
        global AudioIndex, TRACKS
        if self.is_playlist and self.label_2.text() != 'Главная':
            self.remove.setVisible(True)
        else:
            self.remove.setVisible(False)

        AudioIndex = int(row)
        TRACKS.k, PLAYLIST.k = False, False
        TRACKS.set_playlist([i.path() for i in self.tracks_in_main])
        PLAYLIST.set_playlist([i.path() for i in TRACKS.get_playlist()])
        TRACKS.k, PLAYLIST.k = True, True
        self.set_audio()
        self.play_audio()

    def open_main_window(self):
        """Главное окно"""
        self.files.clear()
        self.label_2.setText('Главная')
        TRACKS.set_playlist('restart')
        PLAYLIST.set_playlist('restart')

        self.tracks_in_main = TRACKS.get_playlist()
        self.set_table()

    def open_window_with_playlists(self):
        """Окно с плейлистами"""
        self.shuffle.setVisible(False)
        self.files.clear()
        self.label_2.setText('Плейлисты')
        self.add.setVisible(True)
        self.files.setColumnCount(1)
        self.files.setRowCount(len(self.base.get_playlists()))

        for i, playlist in enumerate(self.base.get_playlists()):
            self.files.setItem(i, 0, QTableWidgetItem(playlist))
        self.connecting(playlist=True)
        self.set_size(True)

    def open_window_with_albums(self):
        """Окно с альбомами"""
        self.shuffle.setVisible(False)
        self.add.setVisible(False)
        self.files.clear()
        self.label_2.setText('Альбомы')
        self.files.setColumnCount(1)
        self.files.setRowCount(len(ALBUMS))
        for i, album in enumerate(ALBUMS):
            self.files.setItem(i, 0, QTableWidgetItem(album))
        self.connecting(album=True)
        self.set_size(True)

    def open_window_with_artists(self):
        """Окно с исполнителями"""
        self.add.setVisible(False)
        self.shuffle.setVisible(False)
        self.files.clear()
        self.label_2.setText('Исполнители')
        self.files.setColumnCount(1)
        self.files.setRowCount(len(ARTISTS))
        for i, artist in enumerate(ARTISTS):
            self.files.setItem(i, 0, QTableWidgetItem(artist))
        self.connecting(artist=True)
        self.set_size(True)

    def connecting(self, artist=False, album=False, playlist=False):
        try:
            self.files.cellPressed.disconnect()
        except TypeError:
            pass
        if self.label_2.text() in ('Главная', 'Плейлисты', 'Исполнители', 'Альбомы'):
            self.remove_playlist.setVisible(False)

        if artist or album or playlist:
            if artist:
                self.artist, self.album, self.playlist = True, False, False
            elif album:
                self.artist, self.album, self.playlist = False, True, False
            elif playlist:
                self.artist, self.album, self.playlist = False, False, True

            self.files.cellPressed.connect(self.selection_by_criterion)
        else:
            self.files.cellPressed.connect(self.start_play)

    def selection_by_criterion(self, row):
        """Выбор по критерию из базы данных"""
        self.is_playlist = False
        if self.artist:
            self.base.get_tracks_by_artist(self.files.item(row, 0).text())
        elif self.album:
            self.base.get_tracks_by_album(self.files.item(row, 0).text())

        if not self.playlist:
            self.label_2.setText(self.base.name)
            self.tracks_in_main = TRACKS.get_playlist().copy()
            self.set_table()

        if self.playlist:
            try:
                self.is_playlist = True

                self.base.get_tracks_by_playlist(self.files.item(row, 0).text())
                self.remove_playlist.setVisible(True)

                self.label_2.setText(self.base.name)
                self.tracks_in_main = TRACKS.get_playlist().copy()
                self.set_table()

            except SyntaxError:
                pass

    def shuffle_tracks(self):
        """Перемешивание"""
        TRACKS.shuffle_playlist()
        PLAYLIST.k = False
        PLAYLIST.set_playlist([i.path() for i in TRACKS.get_playlist()])
        PLAYLIST.k = True
        self.set_audio()
        self.play_audio()

    def add_path_to_txt(self):
        TRACKS.add_path(self)


class PlaylistDialog(QInputDialog):
    """Вспомогательный класс с диалоговыми окнами"""
    def __init__(self):
        super(PlaylistDialog, self).__init__()

    def new_playlist(self, other):
        name, ok_pressed = self.getText(self, 'Новый плейлист', 'Назови свой плейлист')

        other.name = name if ok_pressed and name not in other.get_playlists() else ''

    def add_track(self, other):
        if len(other.get_playlists()) == 0:
            other.add_playlist()
        name, ok_pressed = self.getItem(self, 'Добавить трек',
                                        'Выберите плейлист в который хотите добавить трек',
                                        other.get_playlists(), 0, False)

        other.name = name if ok_pressed else ''


class InformationAboutAudio:
    def __init__(self, other, moment=0):
        global AudioIndex
        self.other = other
        self.file = stagger.read_tag(PLAYLIST.get_playlist()[AudioIndex].path())
        self.print_name()
        self.set_picture()
        self.duration = Duration(other, moment)

    def print_name(self):
        """Вывод на экран информации о играющем треке"""
        global AudioIndex
        #  Название и автор
        title = self.file.title
        if not title:
            title = PLAYLIST.get_playlist()[AudioIndex].path().split('/')[-1]

        artist = self.file.artist
        if not artist:
            artist = 'Неизвестный исполнитель'

        self.other.Title.setText(title)
        self.other.Artist.setText(artist)

    def set_picture(self):
        #  Иллюстрация к альбому и фон
        try:
            by_data = self.file[stagger.id3.APIC][0].data
            im = io.BytesIO(by_data)

            image_file = Image.open(im)
            image_file.save('1.png')
            self.other.Album_pic.setPixmap(QPixmap('1.png'))

            image_file = image_file.filter(ImageFilter.GaussianBlur(radius=5))
            image_file.save('1.png')

            self.other.background.setPixmap(QPixmap('1.png'))

            os.remove('1.png')
        except KeyError:
            try:
                self.other.Album_pic.setPixmap(QPixmap('resources/pictures/music_default.png'))
                self.other.background.setPixmap(QPixmap('resources/pictures/music_blur.png'))
            except AttributeError:
                pass
        except AttributeError:
            pass


class Duration:
    def __init__(self, file, moment=0):
        self.other = file
        self.moment = moment
        self.prev_val = 0
        if self.other.__class__.__name__ != 'PlayerWindow':
            self.val = 0
        else:
            self.val = moment
        self.track_time = datetime.time()
        self.other.player.durationChanged.connect(self.time)
        self.other.Duration.valueChanged.connect(self.get_moment)
        self.timer = QTimer()
        self.run_timer()

    def run_timer(self):
        """Через каждые 0.5 сек ползунок двигается в право"""
        self.timer.timeout.connect(self.on_timer)
        self.timer.start(500)

    def on_timer(self):
        if self.val >= self.other.Duration.maximum():
            self.timer.stop()
            print(self.other.__class__)
            self.other.next_audio()

        elif self.other.player.state() == 1 and not self.other.Duration.isSliderDown():
            self.prev_val = self.val
            self.val = self.other.Duration.value()
            self.val += 500
            self.other.Duration.setValue(self.val)

    def time(self, d):
        self.track_time = datetime.time(minute=d // 1000 // 60, second=d // 1000 % 60)
        self.other.time.setText(str(self.track_time.strftime('%M:%S')))
        self.other.Duration.setMaximum(d - d % 1000)
        if self.other.__class__.__name__ == 'PlayerWindow':
            self.other.Duration.setValue(self.other.main_win.Duration.value())

    def get_moment(self):
        """Используется при перемотке"""
        if self.val - self.prev_val not in (500, 0):
            if self.other.__class__.__name__ == 'PlayerWindow':
                self.other.player.setPosition(self.other.main_win.Duration.value())
                self.other.main_win.Duration.setValue(self.other.Duration.value())
                self.other.main_win.player.setPosition(self.other.Duration.value())
            else:
                self.other.player.setPosition(self.other.Duration.value())
                self.other.Duration.setValue(self.other.Duration.value())


class Player(QFileDialog):
    def __init__(self, files=None, directories=()):
        super(Player, self).__init__()
        self.files = ''
        self.k = True
        self.directories = directories
        self.playlist = []
        self.set_playlist(files)

    def set_playlist(self, files=None):
        """Установка треков в плейлист"""
        if len(self.directories) == 0 and not files:
            self.add_path()

        elif files == 'restart':
            # Перезапуск окна
            for d in PATHS:
                for i in os.listdir(d):
                    url = QUrl(f'{d}/{i}')
                    if i[-4:] in ('.mp3', '.wav', '.ogg') and url not in self.playlist:
                        self.playlist.append(url)

        elif len(self.directories) != 0 and self.k:
            if self.directories.__class__.__name__ in ('list', 'tuple'):
                for d in self.directories:
                    for i in os.listdir(d):
                        url = QUrl(f'{d}/{i}')
                        if i[-4:] in ('.mp3', '.wav', '.ogg') and url not in self.playlist:
                            self.playlist.append(url)
            else:
                for i in os.listdir(self.directories):
                    url = QUrl(f'{self.directories}/{i}')
                    if i[-4:] in ('.mp3', '.wav', '.ogg') and url not in self.playlist:
                        self.playlist.append(url)

        elif files == 1:
            ...

        elif files and files[0].__class__.__name__ == 'QUrl':
            self.playlist = files

        else:
            self.playlist = []
            for i in files:
                url = QUrl(i)
                if url not in self.playlist:
                    self.playlist.append(url)

    def shuffle_playlist(self):
        global AudioIndex
        AudioIndex = 0
        random.shuffle(self.get_playlist())

    def get_playlist(self):
        return self.playlist

    def add_path(self, other=None):
        """Добавить путь, который в будущем будет добавлен автоматически"""
        global PATHS
        self.directories = self.getExistingDirectory(self, 'Выбрать папку', '')
        if self.directories[1] == ':':
            self.directories = self.directories[2:]
        if self.directories not in PATHS:
            self.files = [i for i in os.listdir(self.directories) if i[-4:] in ('.mp3', '.wav', '.ogg')]

            if len(self.files) != 0:
                t = [QUrl(f'{self.directories}/{i}') for i in self.files]
                for i in t:
                    if i not in self.playlist:
                        self.playlist.append(i)
                with open('resources/paths.txt', 'a') as di:
                    di.write(f'"{self.directories}"\n')
                    PATHS.append(f'{self.directories}')
                di.close()
                if other:
                    other.open_main_window()
            else:
                pass
        else:
            pass


def except_hook(cls, exception, traceback):
    sys.__excepthook__(cls, exception, traceback)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    PATHS = []
    # Чтение путей из файла
    with open('resources/paths.txt') as dirs:
        for line in dirs:
            f = line.strip()
            if f != '':
                PATHS.append(eval(f))
    dirs.close()

    AudioIndex = 0  # Индекс играющего в плейлисле трека
    PLAYLIST = Player(directories=PATHS)  # Основной плейлист
    TRACKS = Player(PLAYLIST.get_playlist())  # Вспомогательный плейлист, для работы с таблицей
    ARTISTS, ALBUMS = set(), set()

    ex = MainWindow()
    ex.show()
    sys.excepthook = except_hook
    sys.exit(app.exec_())
