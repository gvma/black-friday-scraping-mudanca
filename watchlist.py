"""Lista de produtos acompanhados.

Cada item tem:
  id        identificador curto (único)
  query     busca enviada ao Zoom (zoom.com.br agrega Amazon, Magalu, Casas Bahia,
            Americanas, Fast Shop, Mercado Livre e outras)
  match     regex que o nome do produto precisa casar (escolhe o modelo certo)
  exclude   regex opcional que descarta resultados (ex.: versões quente/frio)
  quality   nota de qualidade 1-5 — julgamento a partir de guias/reputação da
            marca (Zoom, Buscapé, AnalisaMelhor, my-best etc.). Ajuste à vontade.
  note      por que está na lista / o que observar

Para adicionar um produto, copie um item e ajuste query/match. Rode
`python3 tracker.py --dry-run` para ver qual produto o match escolhe.
"""

CATEGORIES = {
    "ar": {
        "label": "Ar-condicionado split inverter 12.000 BTUs (frio)",
        "quantity": 2,
        "require": r"12\.?000",
        "exclude": r"Port[aá]til|Janela|Quente|Piso|Cassete|Multi|Pe[çc]a|Controle Remoto Universal",
        "tips": [
            "Casa é 220 V: o script já descarta anúncios 110/127 V, mas confira a voltagem na hora de fechar o pedido.",
            "Instalação não está inclusa no preço: orce à parte (normalmente R$ 400–800 por aparelho).",
            "Prefira selo Procel A e gás R-32. Garantia do compressor costuma ser bem maior que a do aparelho.",
        ],
    },
    "robo": {
        "label": "Robô aspirador (120 m², com mapeamento a laser)",
        "quantity": 1,
        "require": r"Rob[ôo]",
        "exclude": r"Pe[çc]a|Filtro|Escova|Kit|Refil|Bateria|Mop de reposi|Acess[óo]rio|Saco",
        "tips": [
            "Para 120 m², priorize LiDAR/laser (mapa por cômodo) e autonomia de 150 min ou mais.",
            "Base autoesvaziante é conforto, não obrigação — encarece bastante.",
        ],
    },
    "louca": {
        "label": "Lava-louças",
        "quantity": 1,
        "exclude": r"Pe[çc]a|Detergente|Secante|Sal |Cesto|Pastilha|Industrial",
        "tips": [
            "8 serviços atende 2–3 pessoas; 14 serviços para 4+ ou quem recebe visitas.",
            "Meça o espaço: as de 14 serviços têm ~60 cm de largura, as de 8 ~45–55 cm de piso/bancada.",
        ],
    },
    "ventilador": {
        "label": "Ventilador de teto",
        "quantity": 1,
        "require": r"Teto",
        "exclude": r"L[âa]mpada|Pe[çc]a|Controle Remoto Universal|Parede|Coluna|Mesa|Circulador",
        "tips": [
            "Motor inverter/DC: muito mais silencioso e consome ~30 W contra ~130 W dos comuns.",
            "Confira altura do pé-direito e tamanho do cômodo (pás de 100–130 cm para quartos/salas).",
        ],
    },
    "tv": {
        "label": "Smart TV 60–70\" (na prática, 65\")",
        "quantity": 1,
        "require": r"(?<![A-Za-z\d])(60|65|70)(?!\d)",  # 65", 65C7L — mas não QNED70A
        "exclude": r"Suporte|Controle Remoto|Cabo|Capa|Pel[íi]cula|Rack|Painel|Conversor|Antena",
        "tips": [
            "60\" praticamente sumiu do mercado e 70\" tem poucas opções; 65\" é o tamanho com mais escolha.",
            "Mini LED (TCL C6K/C7L) tem contraste e brilho bem superiores ao QLED/LED comum — vale a diferença se a sala for clara.",
            "Para jogos/esporte, prefira 120/144 Hz (C6K, C7L).",
        ],
    },
}

ITEMS = [
    # ---------------- Ar-condicionado ----------------
    {"id": "ar-midea-xtreme", "cat": "ar", "quality": 4.5,
     "query": "midea xtreme save connect 12000 btus",
     "match": r"Xtreme Save",
     "note": "O mais citado como custo-benefício: inverter, Wi-Fi, muito econômico."},
    {"id": "ar-midea-ecomaster", "cat": "ar", "quality": 4.0,
     "query": "ar condicionado split midea ai ecomaster 12000",
     "match": r"Ecomaster",
     "note": "Linha mais barata da Midea/Springer, boa eficiência."},
    {"id": "ar-midea-airvolution", "cat": "ar", "quality": 4.0,
     "query": "ar condicionado midea airvolution 12000 inverter",
     "match": r"42EFVCA12M5|AirVolution(?! Lite)",
     "note": "Midea AirVolution — Wi-Fi, costuma ser o mais barato entre os bons."},
    {"id": "ar-lg-voice", "cat": "ar", "quality": 4.5,
     "query": "ar condicionado lg dual inverter voice 12000 frio",
     "match": r"Dual Inverter (AI )?Voice",
     "exclude": r"Artcool",
     "note": "LG Dual Inverter: compressor com 10 anos de garantia, muito econômico."},
    {"id": "ar-lg-compact", "cat": "ar", "quality": 4.0,
     "query": "ar condicionado lg dual inverter compact 12000",
     "match": r"Dual Inverter (AI )?Compact",
     "note": "Versão mais simples/barata da LG, mesmo compressor."},
    {"id": "ar-samsung-windfree", "cat": "ar", "quality": 4.5,
     "query": "ar condicionado samsung windfree 12000 frio",
     "match": r"WindFree",
     "note": "Modo sem vento direto (ótimo para quarto). Costuma ser mais caro."},
    {"id": "ar-elgin-eco2", "cat": "ar", "quality": 3.5,
     "query": "ar condicionado elgin eco ii 12000 inverter",
     "match": r"Eco II",
     "note": "Opção mais barata com boa avaliação; marca com assistência ampla."},
    {"id": "ar-electrolux-coloradapt", "cat": "ar", "quality": 3.5,
     "query": "ar condicionado electrolux color adapt 12000 inverter",
     "match": r"Color Adapt",
     "note": "Frequentemente o mais barato entre os inverter de marca conhecida."},

    # ---------------- Robô aspirador ----------------
    {"id": "robo-xiaomi-x20", "cat": "robo", "quality": 4.5,
     "query": "robo aspirador xiaomi x20",
     "match": r"X20",
     "note": "Xiaomi com base autoesvaziante — conforto extra se cair de preço."},
    {"id": "robo-xiaomi-h40", "cat": "robo", "quality": 4.0,
     "query": "robo aspirador xiaomi h40",
     "match": r"H40",
     "note": "Xiaomi laser, boa autonomia; preço médio."},
    {"id": "robo-xiaomi-s40c", "cat": "robo", "quality": 3.5,
     "query": "robo aspirador xiaomi s40c",
     "match": r"S40C",
     "note": "Laser mais barato da Xiaomi; bateria menor — pode precisar recarregar em 120 m²."},
    {"id": "robo-electrolux-erb80", "cat": "robo", "quality": 3.5,
     "query": "robo aspirador electrolux erb80",
     "match": r"ERB80",
     "note": "Electrolux com laser; assistência técnica nacional."},
    {"id": "robo-midea-m7", "cat": "robo", "quality": 3.5,
     "query": "robo aspirador midea connectlaser m7",
     "match": r"M7",
     "note": "Midea laser, aspira e passa pano."},
    {"id": "robo-kabum-700", "cat": "robo", "quality": 3.5,
     "query": "robo aspirador kabum smart 700",
     "match": r"Smart 700",
     "note": "Laser barato e bem avaliado; marca própria do KaBuM!."},

    # ---------------- Lava-louças ----------------
    {"id": "louca-brastemp-blf08bs", "cat": "louca", "quality": 4.0,
     "query": "lava louças brastemp blf08bs",
     "match": r"BLF08B",
     "note": "8 serviços — o custo-benefício mais citado para casal."},
    {"id": "louca-electrolux-ls08e", "cat": "louca", "quality": 3.5,
     "query": "lava louças electrolux ls08e",
     "match": r"LS08E",
     "note": "8 serviços, compacta."},
    {"id": "louca-electrolux-ll10x", "cat": "louca", "quality": 4.5,
     "query": "lava louças electrolux ll10x",
     "match": r"LL10X",
     "note": "10 serviços, muito bem avaliada — meio-termo de capacidade."},
    {"id": "louca-midea-14", "cat": "louca", "quality": 3.5,
     "query": "lava louças midea 14 serviços",
     "match": r"Midea.*14|14.*Midea",
     "note": "14 serviços mais barata entre as grandes."},
    {"id": "louca-electrolux-ls14e", "cat": "louca", "quality": 4.0,
     "query": "lava louças electrolux ls14e",
     "match": r"LS14E",
     "note": "14 serviços, prática no dia a dia."},
    {"id": "louca-brastemp-blf60", "cat": "louca", "quality": 4.0,
     "query": "lava louças brastemp blf60ar",
     "match": r"BLF60",
     "note": "14 serviços Brastemp."},

    # ---------------- Ventilador de teto ----------------
    {"id": "vent-arno-ultimate", "cat": "ventilador", "quality": 4.5,
     "query": "ventilador de teto arno ultimate",
     "match": r"Ultimate",
     "note": "Muito silencioso, 6 velocidades, controle remoto."},
    {"id": "vent-ventisol-aires-inv", "cat": "ventilador", "quality": 4.0,
     "query": "ventilador de teto ventisol aires inverter",
     "match": r"Aires.*Inverter|Inverter.*Aires",
     "note": "Motor DC ~30 W, silencioso — bom equilíbrio."},
    {"id": "vent-ventisol-fenix-inv", "cat": "ventilador", "quality": 3.5,
     "query": "ventilador de teto ventisol fenix inverter",
     "match": r"F[eê]nix.*Inverter|Inverter.*F[eê]nix",
     "note": "Fênix (o mais vendido do Brasil) na versão inverter."},
    {"id": "vent-ventisol-legacy-inv", "cat": "ventilador", "quality": 3.5,
     "query": "ventilador de teto ventisol legacy inverter",
     "match": r"Legacy.*Inverter|Inverter.*Legacy",
     "note": "Inverter com LED e controle, preço baixo."},

    # ---------------- TV ----------------
    {"id": "tv-tcl-65c7l", "cat": "tv", "quality": 4.5,
     "query": "tv tcl 65c7l",
     "match": r"C7L",
     "note": "Pedido de vocês. QD-Mini LED topo da TCL: brilho alto, 144 Hz, som Bang & Olufsen."},
    {"id": "tv-tcl-65c7k", "cat": "tv", "quality": 4.5,
     "query": "tcl c7k 65",
     "match": r"C7K",
     "note": "Pedido de vocês. QD-Mini LED da geração anterior à C7L, imagem parecida — vale a pena se cair bem abaixo da C7L."},
    {"id": "tv-tcl-65c6k", "cat": "tv", "quality": 4.0,
     "query": "tv tcl 65c6k",
     "match": r"C6K",
     "note": "Mini LED mais barata — costuma ser o melhor custo-benefício em imagem."},
    {"id": "tv-tcl-65p7l", "cat": "tv", "quality": 3.5,
     "query": "tv tcl 65p7l",
     "match": r"P7L",
     "note": "QLED de entrada da TCL (sucessora da P7K, muito recomendada)."},
    {"id": "tv-samsung-65-u8600f", "cat": "tv", "quality": 3.5,
     "query": "tv samsung 65 u8600f",
     "match": r"U8600F",
     "note": "Samsung Crystal de entrada; sistema Tizen bom, imagem básica."},
    {"id": "tv-lg-65-qned70a", "cat": "tv", "quality": 3.5,
     "query": "tv lg qned70a 65",
     "match": r"QNED7",
     "note": "LG QNED de entrada; webOS, boa para streaming."},
]
