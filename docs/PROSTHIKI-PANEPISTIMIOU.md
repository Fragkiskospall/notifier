# Πρόσθεσε το πανεπιστήμιό σου

Ο κατάλογος είναι ένα αρχείο ανά ίδρυμα στο
`src/uniwa_notifier/catalog/universities/`. Για να προσθέσεις ή να διορθώσεις
ένα πανεπιστήμιο, φτιάχνεις ή αλλάζεις αυτό το αρχείο και ανοίγεις pull request.

## Ελάχιστο αρχείο

```toml
id = "upatras"                      # ίδιο με το όνομα αρχείου
name = "Πανεπιστήμιο Πατρών"
short = "ΠΠ"
platform = "openeclass"             # openeclass | moodle | other
support = "eclass"                  # full | eclass | unsupported
verified = 2026-11-20               # πότε το έλεγξες
source = "https://..."              # επίσημη σελίδα που δείχνει τη διεύθυνση

[eclass]
url = "https://eclass.upatras.gr"
auth = "auto"                       # form | cas | auto
```

## Επίπεδα υποστήριξης

| support | Σημαίνει |
|---|---|
| `full` | Ανακοινώσεις, εργασίες, εργαστήρια **και βαθμοί**. Θέλει ενότητα `[grades]` και δοκιμή με πραγματικό λογαριασμό. |
| `eclass` | Ανακοινώσεις και εργασίες. Αρκεί το URL του Open eClass. |
| `unsupported` | Άλλη πλατφόρμα (π.χ. Moodle). Μπαίνει στη λίστα για να ξέρει ο φοιτητής ότι δεν υποστηρίζεται ακόμα. |

## Τμήματα με δικό τους eClass ή RSS

```toml
[[eclass.extra]]
department = "Πληροφορικής"
url = "https://gunet2.cs.unipi.gr"
auth = "cas"

[[departments]]
id = "ice"
name = "Μηχανικών Πληροφορικής και Υπολογιστών"
rss = "https://ice.uniwa.gr/feed/"
```

## Κανόνες

- Μόνο `https://` διευθύνσεις.
- Το `source` πρέπει να είναι επίσημη σελίδα του ιδρύματος ή του τμήματος.
- **Ποτέ** κωδικοί, ονόματα χρηστών ή στοιχεία φοιτητών σε αυτά τα αρχεία.
- Τρέξε `pytest tests/test_catalog.py` πριν ανοίξεις το pull request.
