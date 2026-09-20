# MintGuard

Linux Mint için PySide6 ile geliştirilmiş, güvenli ve seçime dayalı sistem bakım aracı.

## Özellikler

- Diskin dolu/boş alanını ve en büyük kullanıcı önbelleği klasörlerini gösterir.
- İndirilen APT paketlerini temizler (sistem paketlerini kaldırmaz).
- İsteğe bağlı kullanıcı önbelleği temizliği: **varsayılan olarak kapalıdır**; yalnızca seçilen gün sınırından eski, normal dosyaları siler. Sembolik bağlantıları izlemez; klasörleri silmez.
- Journal'ın **7 günden eski arşiv** günlüklerini temizler; etkin journal dosyalarını zorla silmez.
- Kullanıcı ve sistem kapsamındaki kullanılmayan Flatpak bağımlılıklarını kaldırır; **uygulama verilerini silen** --delete-data seçeneğini kullanmaz.
- Tarama ve temizlik arka plan iş parçacığında yapılır. Hata ve yetki reddi başarılı işlem olarak gösterilmez.
- Sistem renk temasına göre açık/koyu görünüm ve dar pencerede tek sütunlu kart düzeni.

> Önemli: Eski önbellek dosyalarının silinmesi uygulamaların yeniden önbellek oluşturmasına yol açabilir. Bazı uygulamalar önbelleği geçici durum saklamak için kullanır. Hangi kategorilerin temizleneceğini kendiniz seçin; önemli verilerin yedeğini tutun.

## Kurulum (Linux Mint 22.x / Ubuntu)

Python 3.10+ ve PySide6 gerekir. Dağıtımın sistem Python'unu değiştirmeden sanal ortam kullanın:

~~~bash
sudo apt install python3-venv python3-pip policykit-1
git clone https://github.com/MOzcelik14/MintGuard.git
cd MintGuard
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python cleaner.py
~~~

APT ve journal temizliği seçilirse **pkexec** üzerinden Polkit yetkilendirme penceresi açılabilir. MintGuard'ı tümüyle root olarak başlatmayın: kullanıcı önbelleği böylece yanlış hesabın altında taranır. Flatpak kurulu değilse ilgili seçenek devre dışıdır. APT, journalctl ya da pkexec erişilebilir değilse işlem raporunda hata gösterilir.

## Testler

Arayüz açmadan çekirdek modül testleri:

~~~bash
python3 -m unittest discover -s tests -v
~~~

Arayüz dahil kurulmuş bağımlılıklarla çalıştırmak için:

~~~bash
.venv/bin/python -m unittest discover -s tests -v
~~~

## Proje yapısı

- cleaner.py: PySide6 arayüzü, responsive kartlar ve arka plan worker'ı.
- modules/maintenance.py: tarama, güvenli dosya seçimi ve bakım komutları.
- tests/: önbellek sınırları ve komut-hata davranışları için testler.

MintGuard temizlikten önce tahmini önbellek miktarını gösterir. Bir işlemin raporunda belirtilen boşaltılan alan *yaklaşıktır*; APT/journal ölçümleri dosyaların durumuna ve etkin günlüklerin varlığına göre değişebilir. Flatpak için kesin bir temizlenebilir alan tahmini sunulmaz.
