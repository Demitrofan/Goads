"""Связь сообщение → объявление: вместо одного объявления — несколько (прайс-листы, списки вещей)."""

import django.db.models.deletion
from django.db import migrations, models


def copy_links(apps, schema_editor):
    Post = apps.get_model("ads", "Post")
    for old, new in (("listing", "listings"), ("moto", "motos"), ("stuff", "stuffs")):
        m2m = Post._meta.get_field(new)
        through = m2m.remote_field.through
        target = m2m.related_model._meta.model_name   # listing / motolisting / stufflisting
        rows = Post.objects.exclude(**{f"{old}_id": None}).values_list("id", f"{old}_id")
        through.objects.bulk_create([through(**{"post_id": p, f"{target}_id": o}) for p, o in rows])


class Migration(migrations.Migration):

    dependencies = [
        ("ads", "0019_post_stuff"),
        ("moto", "0018_motolisting_motophoto"),
        ("stuff", "0002_stufflisting_stuffphoto"),
    ]

    operations = [
        # Старые связи временно переименовываем, чтобы освободить имя "posts"
        migrations.AlterField("post", "listing", models.ForeignKey(
            blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
            related_name="old_posts", to="ads.listing")),
        migrations.AlterField("post", "moto", models.ForeignKey(
            blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
            related_name="old_posts", to="moto.motolisting")),
        migrations.AlterField("post", "stuff", models.ForeignKey(
            blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
            related_name="old_posts", to="stuff.stufflisting")),
        migrations.AddField("post", "listings", models.ManyToManyField(
            blank=True, related_name="posts", to="ads.listing")),
        migrations.AddField("post", "motos", models.ManyToManyField(
            blank=True, related_name="posts", to="moto.motolisting")),
        migrations.AddField("post", "stuffs", models.ManyToManyField(
            blank=True, related_name="posts", to="stuff.stufflisting")),
        migrations.RunPython(copy_links, migrations.RunPython.noop),
        migrations.RemoveField("post", "listing"),
        migrations.RemoveField("post", "moto"),
        migrations.RemoveField("post", "stuff"),
    ]
