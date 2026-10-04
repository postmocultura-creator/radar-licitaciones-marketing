#!/bin/sh
# Publica en la rama "estado" los ficheros que se le pasen, encima de lo que
# ya hay en ella, como un único commit sin historia: cada noche sustituye al
# anterior y la rama no crece (los datos internos del pipeline pesan ~50 MB
# y se reescriben a diario; en main hacían crecer el repositorio 2-5 MB por
# noche). Lo usan los dos workflows de datos.
#
#   sh .github/publicar_estado.sh data/a.json data/b.json ...
#
# Los ficheros que no existan se ignoran (y conservan lo que ya hubiera en
# la rama). Necesita git config user.name/user.email.
set -e
REF=refs/remotes/origin/estado
# Lo más reciente de la rama justo antes de escribir: si el otro workflow la
# ha tocado mientras tanto, se conserva lo suyo y solo se cambia lo nuestro.
# "+": la rama se reescribe cada vez; sin él, el fetch se negaría en silencio
# y se publicaría encima de una versión vieja.
git fetch --depth=1 origin "+estado:$REF" 2>/dev/null || true
export GIT_INDEX_FILE="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/estado.index"
rm -f "$GIT_INDEX_FILE"
if git rev-parse -q --verify "$REF" >/dev/null; then
  git read-tree "$REF"
else
  git read-tree --empty
fi
for f in "$@"; do
  if [ -f "$f" ]; then git add -f "$f"; fi
done
arbol=$(git write-tree)
if git rev-parse -q --verify "$REF" >/dev/null && [ "$arbol" = "$(git rev-parse "$REF^{tree}")" ]; then
  echo "Estado sin cambios"
  exit 0
fi
commit=$(git commit-tree "$arbol" -m "Estado del pipeline $(date -u +%Y-%m-%d)")
git push -f origin "$commit:refs/heads/estado"
echo "Estado publicado: $commit"
