# cpumarks
Acquiert et exploite des données d'***indice CPU*** pour usage dans les audits

# Fonctions principales

## Acquisition des données

- lecture des données sur [cpubenchmark.net](https://www.cpubenchmark.net)
- extraction de l'information utile
- traitement de cette information (suppression des doublons, mise enforme des données numériques)
- création d'un fichier CSV exploitable pour une recherche fiable de l'indice d'un CPU donné

Cette fonction est dans le répertoire `marksdata`

## Recherche de l'indice d'un CPU donné

Cette fonction recherche l'indice d'un CPU donné *dans un fichier CSV tel que décrit ci-dessus*.

En cas d'échec, la recherche renvoie un indice nul ainsi que des données qui serviront à affiner l'algorithme.

Cette fonction est dans le répertoire `marklookup`


# Utilisation

Ce code est utilisé par l'API qui propose un *entry point* renvoyant l'indice d'un CPU donné.

Ci-dessous un exemple d'utilisation locale:
```
$ python3 marklookup/get_mark_of_cpu.py -c "Intel Celeron G5925 (3.6 GHz)" \
    --cpuscsv marksdata/cpumarks-20251106.150008.csv --json | jq -r '.'
{
  "error": false,
  "mark": "2808",
  "cpustr": "Intel Celeron G5925 (3.6 GHz)",
  "hint": "DESPERATE_1",
  "cpuscsv": "cpumarks-20251106.150008.csv",
  "linenum": "2165",
  "line": "Intel Celeron G5925 @ 3.60GHz",
  "details": []
}
$ 
```

L'absence d'autre documentation est ici *volontaire*. N'hésitez pas à contacter les auteurs en cas de besoin.
