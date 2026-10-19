"""Заполняет модель по справочнику и пометку «из прайс-листа» у уже собранных байков; машины снимает."""
from django.db import migrations
from django.utils import timezone


def fill(apps, schema_editor):
    from moto.catalog import family_of, is_car
    MotoListing = apps.get_model("moto", "MotoListing")
    Post = apps.get_model("ads", "Post")
    Through = Post.motos.through
    by_post = {}
    for post_id, moto_id in Through.objects.values_list("post_id", "motolisting_id"):
        by_post.setdefault(post_id, set()).add(moto_id)
    list_ids = {m for ids in by_post.values() if len(ids) > 1 for m in ids}
    now = timezone.now()
    for m in MotoListing.objects.all():
        m.family = family_of(m.model_name)
        m.from_list = m.pk in list_ids
        fields = ["family", "from_list"]
        if is_car(m.model_name) and not m.closed:
            m.closed = now
            fields.append("closed")
        m.save(update_fields=fields)


class Migration(migrations.Migration):
    dependencies = [
        ("moto", "0021_family_from_list"),
        ("ads", "0026_listing_region_phuket"),
    ]
    operations = [migrations.RunPython(fill, migrations.RunPython.noop)]
