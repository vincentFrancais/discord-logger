from discord_webhook import DiscordWebhook, DiscordEmbed


def embed_to_json(embed: DiscordEmbed):
    dummy_wh = DiscordWebhook(url='https://dummy.com')
    dummy_wh.add_embed(embed)
    return dummy_wh.json


def compare_dict(d1: dict, d2: dict):
    if d1 is None and d2 is None:
        return True
    if d1 is None or d2 is None:
        return False
    keys = d1.keys()
    for key in keys:
        assert d1[key] == d2[key]
    return True


def compare_fields(f1: list[dict], f2: list[dict]):
    assert len(f1) == len(f2)
    for i in range(len(f1)):
        assert compare_dict(f1[i], f2[i])
    return True


def compare_emdeds(emb1: DiscordEmbed, emb2: DiscordEmbed) -> bool:
    assert emb1.title == emb2.title
    assert emb1.description == emb2.description
    assert emb1.color == emb2.color
    dicts_to_compare = ['author', 'footer', 'image', 'thumbnail', 'provider', 'video']
    for d in dicts_to_compare:
        assert compare_dict(getattr(emb1, d), getattr(emb2, d))
    assert compare_fields(emb1.fields, emb2.fields)
    return True
