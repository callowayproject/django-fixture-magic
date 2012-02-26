from optparse import make_option

from django.core.exceptions import FieldError, ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError
from django.core.serializers import serialize
from django.db.models import loading

from fixture_magic.utils import (add_to_serialize_list, serialize_me,
        serialize_fully)


class Command(BaseCommand):
    help = ('Dump specific objects from the database into JSON that you can '
            'use in a fixture')
    args = "<[--kitchensink | -k] object_class id1 [id2 [...]]>"

    option_list = BaseCommand.option_list + (
            make_option('--kitchensink', '-k',
                action='store_true', dest='kitchensink',
                default=False,
                help='Attempts to get related objects as well.'),
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
        else:
            objs = dump_me.objects.all()

        main_model = main_model.lower()
        serialization_order = []
        if options.get('kitchensink'):
            # Recursively serialize all related objects.
            priors = set()
            queue = list(objs)
            while queue:
                obj = queue.pop(0)
                
                # Abort cyclic references.
                if obj in priors:
                    continue
                priors.add(obj)
                
                # Skip ignored models.
                rel_name = obj._meta.app_label+'.'+obj._meta.module_name
                rel_name = rel_name.lower()
                if rel_name in exclude_list:
                    continue
                
                # Skip models not specifically being filtered by.
                if rel_name != main_model and filter_list and rel_name not in filter_list:
                    continue
                
                # Queue current object to be serialized
                serialization_order.append(obj)
                
                # Serialize relations.
                related_fields = [
                    rel.get_accessor_name()
                    for rel in obj._meta.get_all_related_objects()
                ]
                for rel in related_fields:
                    try:
                        related_objs = obj.__getattribute__(rel).all()
                        for rel_obj in related_objs:
                            if rel_obj in priors:
                                continue
                            queue.append(rel_obj)
                    except FieldError:
                        pass
                    except ObjectDoesNotExist:
                        pass
                    
        else:
            # Only serialize the immediate objects.
            serialization_order = objs
            
        #add_to_serialize_list(objs)
        add_to_serialize_list(reversed(serialization_order))
        serialize_fully()
        print serialize('json', [o for o in serialize_me if o is not None],
                        indent=4, use_natural_keys=options['natural'])
