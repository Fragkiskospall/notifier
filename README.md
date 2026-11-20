# Notifier

Ειδοποιήσεις για φοιτητές ελληνικών πανεπιστημίων. Ο Notifier ελέγχει για σένα
το Open eClass, το site του τμήματος και την πύλη φοιτητών, και σε ειδοποιεί
στο κινητό ή στον υπολογιστή μόνο για ό,τι άλλαξε.

Μέρος του [FragkiskOSource](https://fragkiskospall.github.io). Δωρεάν, ανοιχτός
κώδικας (MIT), χωρίς server, χωρίς λογαριασμούς, χωρίς analytics.

| Τι | Πότε |
|---|---|
| Νέες ανακοινώσεις (μαθήματα eClass και RSS τμήματος) | κάθε 30′ |
| Σύνοψη εργασιών με προθεσμίες | 08:00, 14:00, 21:00 (ρυθμίζεται) |
| Υπενθύμιση εργαστηρίου, από τις ομάδες χρηστών | το πρωί της ημέρας |
| Νέος βαθμός στην πύλη φοιτητών | κάθε 30′ (όπου υποστηρίζεται) |

## Λήψη

Από τα [Releases](../../releases/latest):

- **macOS:** `FragkiskOSource-Notifier-macos.zip`. Σύρε το app στο **/Applications**
  (όχι στα Downloads) και την πρώτη φορά άνοιξέ το με **δεξί κλικ → Άνοιγμα**.
- **Windows:** `FragkiskOSource-Notifier-windows.zip`. Αποσυμπίεσε και άνοιξε το
  `FragkiskOSource Notifier.exe`. Αν δεις «Windows protected your PC», πάτα
  **More info → Run anyway**.

Οι προειδοποιήσεις εμφανίζονται επειδή τα εκτελέσιμα δεν είναι ακόμα υπογεγραμμένα.
Χτίζονται δημόσια από αυτόν τον κώδικα, στο [release.yml](.github/workflows/release.yml).

## Πανεπιστήμια

| Υποστήριξη | Ιδρύματα |
|---|---|
| Πλήρης (και βαθμοί) | ΠΑΔΑ |
| Ανακοινώσεις, εργασίες, εργαστήρια | ΕΚΠΑ, Πατρών, Πειραιώς, Θεσσαλίας, ΔΠΘ, Πελοποννήσου, ΟΠΑ, Χαροκόπειο, Δυτικής Μακεδονίας, Μακεδονίας, Αιγαίου, ΕΛΜΕΠΑ, Πολυτεχνείο Κρήτης, Ιόνιο, Πάντειο, ΑΣΚΤ |
| Όχι ακόμα (Moodle) | ΕΜΠ, ΑΠΘ, Κρήτης |

Λείπει το δικό σου ή θέλεις βαθμούς; Δες το [docs/PROSTHIKI-PANEPISTIMIOU.md](docs/PROSTHIKI-PANEPISTIMIOU.md).

## Απόρρητο

| Δεδομένο | Πού ζει | Ποιος το βλέπει |
|---|---|---|
| Κωδικοί πανεπιστημίου | Keychain (Mac) / Credential Manager (Windows) | Μόνο εσύ |
| Ρυθμίσεις και ιστορικό | Φάκελος εφαρμογής, κρυπτογραφημένο με AES-256-GCM | Μόνο εσύ |
| Push στο κινητό | Περνά από το ntfy.sh, χωρίς περιεχόμενο σε ιδιωτική λειτουργία | Κανείς το κείμενο |
| Εμείς | Δεν υπάρχει server | Τίποτα |

Η εφαρμογή μιλά μόνο με το πανεπιστήμιό σου και, αν το ενεργοποιήσεις, με το ntfy.
Η «Διαγραφή όλων» στον launcher σβήνει ελέγχους, κωδικούς, ρυθμίσεις και ιστορικό.

## Για developers

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,launcher]"
fragkiskosource-notifier                     # ο launcher
python -m uniwa_notifier check --dry-run -v  # ένα job από τη γραμμή εντολών
pytest && ruff check src tests scripts packaging
```

```
src/uniwa_notifier/
  launcher/   οθόνες (PySide6) και λογική εγκατάστασης
  system/     ό,τι αλλάζει ανά λειτουργικό: jobs (launchd / Task Scheduler), ειδοποιήσεις
  catalog/    κατάλογος πανεπιστημίων, ένα TOML ανά ίδρυμα
  eclass/     σύνδεση και ανάγνωση σελίδων του Open eClass
  services/   πύλη φοιτητών (βαθμοί)
  jobs/       ανακοινώσεις, σύνοψη, εργαστήρια, βαθμοί
  vault.py    κρυπτογραφημένο state
tests/        pytest με ανωνυμοποιημένες πραγματικές σελίδες
```

Τα tests τρέχουν σε Linux, Windows και macOS σε κάθε pull request.

## Άδεια

[MIT](LICENSE). Δεν συνδέεται με κανένα πανεπιστήμιο ή με το GUnet.
