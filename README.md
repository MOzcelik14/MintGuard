# MintGuard 2.0

**Linux Mint için modern, açık kaynak sistem sağlığı ve temizlik merkezi.** Python / PySide6 ile geliştirilmiştir.

## Neler yapar?

| Ekran | İşlev |
|---|---|
| Genel Bakış | CPU kullanım grafiği; RAM, swap, zram, pil sağlığı ve kök disk doluluğu. |
| Temizlik | APT paket önbelleği, kullanıcı önbelleği, journal, kullanılmayan Flatpak bağımlılıkları, eski küçük resimler ve çöp kutusu. |
| Depolama | Ev klasöründeki büyük dosyalar ve klasörler; çöp kutusu / thumbnail / tarayıcı önbelleklerinin tahmini boyutları. |
| Sistem | Dağıtım, kernel, NVIDIA sürücüsü, çalışma süresi, yerel bakım geçmişi ve isteğe bağlı GitHub sürüm kontrolü. |

- Türkçe/İngilizce arayüz (dil tuşu sol alt menüdedir); sistem temasına uygun açık/koyu renkler.
- Tarama ve temizlik QThread üzerinden yürütülür, kullanıcı arayüzünün uzun disk işlemleri sırasında kilitlenmesi önlenir.
- Bakım geçmişi yalnızca kendi cihazında `~/.local/state/mintguard/history.json` içinde tutulur (en fazla 100 kayıt).
- Sürüm kontrolü **ancak düğmeye basıldığında** GitHub'a bağlanır; arka planda telemetri/izleme servisi yoktur.

## Güvenlik

- Tüm temizlikler seçim ve onay gerektirir. Kullanıcı önbelleği, eski küçük resimler, Flatpak ve çöp kutusu **varsayılan olarak seçili değildir**.
- Önbellek temizliği yalnızca seçilen gün sayısından **eski normal dosyaları** siler; symlink ve dizinleri silmez. Uygulama kullanımdayken dosyalarını korumak için önbelleği temizlemeyin.
- **Kişisel dosya analizi salt okunurdur**; büyük dosyalar, kernel ve Timeshift yedekleri otomatik silinmez.
- Disk taraması ev dizininde en fazla **250.000 normal dosyayı** sayar; sınıra ulaşırsa sonuçların eksik olabileceğini belirtir. Sembolik klasörlere ve ayrı bağlama noktalarına girmez.
- APT `autoremove` yalnızca **simülasyonla öneri sunar**; otomatik çalıştırılmaz.
- Flatpak temizlik komutu uygulama verilerini silen `--delete-data` kullanmaz.
- Çöp kutusu boşaltılması geri alınamaz ve ikinci onay gerektirir. `gio trash --empty` tüm kullanıcı çöp kutularını (bağlı diskler dahil) boşaltabilir.
- Yetki gerektiren işlemler `pkexec` ile ayrı yürütülür; hata durumunda işlem başarılı sayılmaz.

## Çalıştırma (kaynak kodundan)

Linux Mint 22.x / Ubuntu 24.04 veya benzeri, Python 3.10+:

~~~bash
sudo apt install python3-venv python3-pip policykit-1
git clone https://github.com/MOzcelik14/MintGuard.git
cd MintGuard
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python cleaner.py
~~~

MintGuard'ı `sudo python cleaner.py` ile başlatmayın: yanlış kullanıcı ev dizini ve yetkileriyle çalışır.

## .deb kurulumu

[GitHub Actions](https://github.com/MOzcelik14/MintGuard/actions) üzerinde başarılı **MintGuard checks** çalışmasının `mintguard-deb` artifact'ı indirilebilir. Bir `v2.0.0` etiketi yayımlandığında başarılı test + derleme sonrasında [Releases](https://github.com/MOzcelik14/MintGuard/releases) sayfasına otomatik `mintguard_2.0.0_amd64.deb` eklenir.

~~~bash
sudo apt install ./mintguard_2.0.0_amd64.deb
~~~

Paket x86_64/amd64 mimarisi içindir ve `/opt/mintguard` altında PyInstaller ile paketlenmiş uygulamayı, Cinnamon uygulama menüsü girdisini ve MintGuard simgesini içerir. Paket Ubuntu **24.04 üzerinde** üretilir; Mint 22.x için hedeflenmiştir. Gerçek Mint bilgisayarında ayrıca doğrulama tavsiye edilir.

Yerel .deb üretimi için, önce PyInstaller kurulup proje kökünde şu komutlar yürütülür:

~~~bash
.venv/bin/python -m pip install pyinstaller
.venv/bin/pyinstaller --noconfirm --clean --windowed --onedir --name mintguard cleaner.py
.venv/bin/python packaging/build_deb.py
~~~

## Testler

~~~bash
python3 -m unittest discover -s tests -v
~~~

CI: Python derlemesi, bakım testleri, ekran olmadan PySide6 smoke testi, PyInstaller ve .deb paket kontrolü.

## Kaynak düzeni

- `cleaner.py`: dört ekranlı Qt arayüzü.
- `modules/maintenance.py`: eski bakım motoru.
- `modules/system_info.py`: Linux sağlık metrikleri.
- `modules/storage.py`: sınırlı ve salt-okunur dosya analizi.
- `modules/advanced_cleanup.py`: isteğe bağlı thumbnail/çöp kutusu temizliği ve APT simülasyonu.
- `modules/i18n.py`, `modules/history.py`: diller, geçmiş ve güncelleme denetimi.
- `packaging/build_deb.py`: .deb paketleme.
- `assets/mintguard.svg`: uygulama ikonu.

**Not:** Bu araç büyük dosyalar için yalnızca bilgi verir. Silme kararı ve yedek sorumluluğu kullanıcıya aittir.
