#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-data}"
OUT="${2:-reports/coa_diagnostic_report.txt}"

mkdir -p "$(dirname "$OUT")"

known_names="Bellowing Voice|Headhunter's Spear|Hodir's Wrath|Barbaric Rage|Falconstrike|Chronomancer|Barbarian|Vol'Jin Alpha"
data_keys="self.__next_f|runtimeBuildProcess|api/v3 builder CoA parser|classId|className|tabId|tabName|talents|nodes|spellId|spell_id|talentEssence|abilityEssence|requires [0-9]+ Talent Essence"
class_names="Barbarian|Witch Doctor|Felsworn|Witch Hunter|Stormbringer|Knight of Xoroth|Guardian|Templar|Bloodmage|Ranger|Chronomancer|Necromancer|Pyromancer|Cultist|Starcaller|Sun Cleric|Tinker|Primalist|Venomancer|Reaper"

{
  echo "===== CoA capture diagnostic report ====="
  echo "Generated: $(date -Is)"
  echo "Root: $ROOT"
  echo

  echo "===== File inventory summary ====="
  find "$ROOT" -type f \
    -printf '%s\t%p\n' 2>/dev/null \
    | sort -nr \
    | awk '
      BEGIN { printf "%-12s %s\n", "SIZE", "PATH" }
      {
        size=$1
        path=$2
        for (i=3; i<=NF; i++) path=path " " $i
        printf "%-12s %s\n", human(size), path
      }
      function human(x) {
        if (x > 1073741824) return sprintf("%.1fG", x/1073741824)
        if (x > 1048576) return sprintf("%.1fM", x/1048576)
        if (x > 1024) return sprintf("%.1fK", x/1024)
        return x "B"
      }
    ' \
    | head -80

  echo
  echo "===== Files containing known CoA names ====="
  rg -a -l "$known_names" "$ROOT" || true

  echo
  echo "===== Files containing likely builder-data keys ====="
  rg -a -l "$data_keys" "$ROOT" || true

  echo
  echo "===== Match counts by file: known names ====="
  rg -a --count-matches "$known_names" "$ROOT" || true

  echo
  echo "===== Match counts by file: data keys ====="
  rg -a --count-matches "$data_keys" "$ROOT" || true

  echo
  echo "===== Class-name hit counts ====="
  rg -a -o "$class_names" "$ROOT" \
    | sed 's/^.*://' \
    | sort \
    | uniq -c \
    | sort -nr || true

  echo
  echo "===== Small context around canonical payload hints ====="
  rg -a -n -C 2 "runtimeBuildProcess|api/v3 builder CoA parser|Vol'Jin Alpha|classId|className" "$ROOT" \
    | head -300 || true

  echo
  echo "===== Rendered talent-node aria-label samples ====="
  rg -a -o 'aria-label="[^"]*(Talent Essence|Ability Essence|requires one connected node)[^"]*"' "$ROOT" \
    | sed 's/&quot;/"/g; s/&amp;/\&/g' \
    | sort -u \
    | head -200 || true

} > "$OUT"

echo "Wrote $OUT"
