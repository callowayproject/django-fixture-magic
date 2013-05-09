import sys
import re
from optparse import make_option
from collections import defaultdict

from django.core.exceptions import FieldError, ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError
from django.core.serializers import serialize
from django.db.models import loading, ForeignKey

from fixture_magic.utils import (
    add_to_serialize_list,
    serialize_me,
    serialize_fully,
    get_key,
)


class Command(BaseCommand):
    help = ('Dump specific objects from the database into JSON that you can '
            'use in a fixture')
    args = "<[--kitchensink | -k] object_class id1 [id2 [...]]>"

    option_list = BaseCommand.option_list + (
            make_option('--kitchensink', '-k',
                action='store_true', dest='kitchensink',
                default=False,
                help='Attempts to get related objects as well.'),
            make_option('--kitchensink-depth',
                dest='kitchensink_depth',
                default=None,
                help='Max depth related objects to get'),
            make_option('--kitchensink-limit',
                dest='kitchensink_limit',
                default=None,
                help='Max number related objects to get'),
            make_option('--just-fk-kitchensink', '-j',
                action='store_true', dest='just_fk_kitchensink',
                default=False,
                help='Only gets fk related objects.'),
            make_option('--limit', '-l',
                dest='limit',
                default=None,
                help='number of models to store, taken randomly'),
            make_option('--natural', '-n',
                action='store_true', dest='natural',
                default=False,
                help='Use natural keys if they are available.'),
            make_option('--exclude_list', '-e',
                dest='exclude_list',
                default='',
                help='A list of model names, formatted as app_name.model_name, to exclude by.'),
            make_option('--filter_list', '-f',
                dest='filter_list',
                default='',
                help='A list of model names, formatted as app_name.model_name, to filter by.'),
            )

    def handle(self, *args, **options):
        error_text = ('%s\nTry calling dump_object with --help argument or use'+
                ' the following arguments:\n %s' %self.args)
        try:
            #verify input is valid
            main_model = args[0]
            (app_label, model_name) = main_model.split('.')
            ids = args[1:]
#            assert(ids)
        except IndexError:
            raise CommandError(error_text %'No object_class or id arguments supplied.')
        except ValueError:
            raise CommandError(error_text %("object_class must be provided in"+
                    " the following format: app_name.model_name"))
        except AssertionError:
            raise CommandError(error_text %'No id arguments supplied.')

        exclude_list = [
            _.strip()
            for _ in options['exclude_list'].replace(' ',',').split(',')
            if _.strip()
        ]

        filter_list = [
            _.strip()
            for _ in options['filter_list'].replace(' ',',').split(',')
            if _.strip()
        ]

        # Lookup initial model.
        dump_me = loading.get_model(app_label, model_name)
        
        # Lookup initial model records.
        if ids:
            try:
                objs = dump_me.objects.filter(pk__in=[int(i) for i in ids])
            except ValueError:
                # We might have primary keys that are just strings...
                objs = dump_me.objects.filter(pk__in=ids)
        elif options.get('limit'):
            limit = int(options.get('limit'))
            objs = dump_me.objects.order_by('?')[:limit]
        else:
            objs = dump_me.objects.all()

        main_model = main_model.lower()
        depends_on = defaultdict(set) # {key:set(keys being pointed to)}
        key_to_object = {}
        serialization_order = []
        max_depth = options.get('kitchensink_depth')
        max_depth = int(max_depth) if max_depth is not None else None
        if options.get('kitchensink') or options.get('just_fk_kitchensink'):
            # Recursively serialize all related objects.
            priors = set()
            queue = list(objs)
            queue = zip(queue, [0]*len(queue)) #queue is obj, depth
            while queue:
                obj, depth = queue.pop(0)

                
                # Abort cyclic references.
                if obj in priors:
                    continue
                priors.add(obj)

                obj_key = get_key(obj)
                key_to_object[obj_key] = obj
                
                # Skip ignored models.
                rel_name = obj._meta.app_label+'.'+obj._meta.module_name
                rel_name = rel_name.lower()
                if rel_name in exclude_list:
                    continue
                
                # Skip models not specifically being filtered by.
                if rel_name != main_model and filter_list and rel_name not in filter_list:
                    continue
                
                #abort max depth in kitchensink
                abort_max_depth = False
                if max_depth is not None and depth > max_depth:
                    abort_max_depth = True

                # Serialize relations.
                if options.get('just_fk_kitchensink') or abort_max_depth:
                    related_fields = []
                else:
                    related_fields = [
                        rel.get_accessor_name()
                        for rel in obj._meta.get_all_related_objects()
                    ] + [
                        m2m_rel.name
                        for m2m_rel in obj._meta.many_to_many
                    ]

                kitchensink_limit = options.get('kitchensink_limit')
                kitchensink_limit = int(kitchensink_limit) if kitchensink_limit is not None else None
                for rel in related_fields:
                    try:
                        related_objs = obj.__getattribute__(rel).all()
                        if kitchensink_limit:
                            related_objs = related_objs[:kitchensink_limit]
                        for rel_obj in related_objs:
                            if rel_obj in priors:
                                continue
                            rel_key = get_key(rel_obj)
                            key_to_object[rel_key] = rel_obj
                            depends_on[rel_key].add(obj_key)
                            queue.append((rel_obj, depth+1))
                    except FieldError:
                        pass
                    except ObjectDoesNotExist:
                        pass
                
                # Serialize foreign keys.
                for field in obj._meta.fields:
                    if isinstance(field, ForeignKey):
                        fk_obj = obj.__getattribute__(field.name)
                        if fk_obj:
                            fk_key = get_key(fk_obj)
                            key_to_object[fk_key] = fk_obj
                            depends_on[obj_key].add(fk_key)
                            queue.append((fk_obj, depth+1))
                
                # Serialize current object.
                serialization_order.append(obj)

        else:
            # Only serialize the immediate objects.
            serialization_order = objs
        
        # Order serialization so that dependents come after dependencies.
        def cmp_depends(a, b):
            if a in depends_on[b]:
                return -1
            elif b in depends_on[a]:
                return +1
            return cmp(get_key(a, as_tuple=True), get_key(b, as_tuple=True))
        serialization_order = list(serialization_order)
        serialization_order.sort(cmp=cmp_depends)
        add_to_serialize_list(serialization_order)
        
        output = serialize('json', [o for o in serialize_me if o is not None],
                        indent=4, use_natural_keys=options['natural'])
        # Remove primary keys so records will not conflict with future existing
        # models, relying on natural keys to resolve ambiguity.
        if options['natural']:
            matches = re.findall('"pk":\s*[0-9]+,', output)
            for match in matches:
                output = output.replace(match, '"pk": null,')
        return output
