from mcdreforged.api.all import PluginServerInterface, PluginCommandSource, PlayerCommandSource, CommandSource, CommandContext, Info, new_thread, SimpleCommandBuilder, Text, Integer, RText, RTextList, RAction, RColor
from where2go.utils.waypoints import WaypointManager, Waypoint, Display
from where2go.utils.api import PlayerAPI
from where2go.utils.display_utils import rtr, help_msg
from where2go.constants import PLUGIN_ID
from where2go.config import CONFIG
import re


class Proxy:

    def __init__(self, server: PluginServerInterface) -> None:
        self.config : CONFIG = server.load_config_simple("config.json", target_class=CONFIG)
        self.waypoint_manager : WaypointManager = WaypointManager(server)
        self.api = PlayerAPI(self.config.player_api)

        prefix = self.config.command.waypoints
        self.prefix = prefix
        builder = SimpleCommandBuilder()
        builder.command(f"{prefix}", self.help_msg) # wp help
        builder.command(f"{prefix} help", self.help_msg)
        builder.arg("waypoint", Text) # wp add
        builder.command(f"{prefix} add", lambda source, context: source.reply(help_msg("add", prefix)))
        builder.command(f"{prefix} add <waypoint>", self.add)
        builder.command(f"{prefix} forceadd", lambda source, context: source.reply(help_msg("forceadd", prefix)))
        builder.command(f"{prefix} forceadd <waypoint>", lambda source, context: self.add(source, context, force=True))
        builder.arg('pos_x', Integer) # wp addpos
        builder.arg('pos_y', Integer)
        builder.arg('pos_z', Integer)
        builder.arg('dimension', Text)
        builder.arg('name', Text)
        builder.command(f"{prefix} addpos", lambda source, context: source.reply(help_msg("addpos", prefix)))
        builder.command(f"{prefix} addpos <pos_x> <pos_y> <pos_z> <dimension> <name>", lambda source, context: self.add(source, context, from_pos=True))
        builder.arg("id", Text) # wp remove
        builder.command(f"{prefix} remove", lambda source, context: source.reply(help_msg("remove", prefix)))
        builder.command(f"{prefix} remove <id>", self.remove)
        builder.command(f"{prefix} info", lambda source, context: source.reply(help_msg("info", prefix)))
        builder.command(f"{prefix} info <id>", self.info)
        builder.arg("page", Text) # wp list
        builder.command(f"{prefix} list", self.list)
        builder.command(f"{prefix} list <page>", self.list)
        builder.arg("name", Text) # wp search
        builder.command(f"{prefix} search", lambda source, context: source.reply(help_msg("search", prefix)))
        builder.command(f"{prefix} search <name>", self.search)
        here_prefix = self.config.command.here # here
        builder.command(f"{here_prefix}", lambda source, context: self.player_pos(source, context, source.player) if source.is_player else None)
        builder.arg("player", Text)
        whereis_prefix = self.config.command.whereis # vris
        builder.command(f"{whereis_prefix}", lambda source, context: source.reply(RTextList(RText(f"§7{whereis_prefix} <player>").c(RAction.suggest_command, f"{whereis_prefix}"), " ", rtr(f"help.whereis"))))
        builder.command(f"{whereis_prefix} <player>", lambda source, context: self.player_pos(source, context, context["player"]))
        builder.register(server)

        server.register_help_message(prefix, rtr("help.wp"))
        server.register_help_message(here_prefix, rtr("help.here"))
        server.register_help_message(whereis_prefix, rtr("help.whereis"))
        fastsearch_prompt = self.config.command.fastsearch_prompt
        server.register_help_message(fastsearch_prompt, rtr("help.fastsearch", prompt=fastsearch_prompt))

        Display._click_event_format = self.config.xaero.click_event_format
    

    def help_msg(self, source: CommandSource, context: CommandContext):
        for i in ["add", "forceadd", "addpos", "remove", "list", "search", "info"]:
            source.reply(help_msg(i, self.prefix))


    def add(self, source: CommandSource, context: CommandContext, force=False, from_pos=False):
        if from_pos:
            DIMS = {"o": "overworld", "n": "the_nether", "e": "the_end"}
            dimension = context["dimension"]
            if dimension in DIMS:
                dimension = DIMS[dimension]
            else:
                for dim in DIMS.values():
                    if dim.endswith(dimension):
                        dimension = dim
                        break
                else:
                    source.reply(rtr("command.add.fail.dimension_invalid"))
                    return
            waypoint = Waypoint((context["pos_x"], context["pos_y"], context["pos_z"]), dimension, context["name"])
        else:
            waypoint : Waypoint = Waypoint.transform_xaero_waypoint(context["waypoint"])
            if not waypoint:
                source.reply(Display.waypoint_error())
                return
        search = self.waypoint_manager.search_distance(waypoint.pos, waypoint.dimension, 0)
        if search:
            search = search[0]
            source.reply(rtr("command.add.fail.waypoint_exist"))
            source.reply(Display.show(search["waypoint"], search["id"]))
            return
        search = self.waypoint_manager.search_distance(waypoint.pos, waypoint.dimension, 32)
        if not force and search:
            source.reply(RTextList(rtr("command.add.fail.waypoint_close"), " ", rtr("command.add.fail.forceadd").c(RAction.run_command, f"{self.prefix} forceadd {context['waypoint']}")))
            for i in search:
                source.reply(RTextList("%.1fm "%waypoint.distance(i["waypoint"].pos), Display.show(i["waypoint"], i["id"])))
            return
        creater = source.player if source.is_player else "[Server]"
        data = self.waypoint_manager.add(creater, waypoint)
        source.reply(rtr("command.add.success", id=data["id"]))
        source.reply(Display.show(waypoint, data["id"]))
            
    
    def remove(self, source: CommandSource, context: CommandContext):
        waypoint = self.waypoint_manager.remove(context["id"])
        if waypoint:
            source.reply(rtr("command.remove.success"))
            source.reply(Display.show(waypoint["waypoint"]))
        else:
            source.reply(rtr("command.remove.fail"))
    

    def list(self, source: CommandSource, context: CommandContext):
        if "page" in context.keys():
            page = context["page"]
            if not re.fullmatch("[0-9]+", page):
                source.reply(rtr("command.list.page_error"))
                return
            page = int(page)
        else:
            page = 1
        page = int(page)
        data = self.waypoint_manager.data
        total = (len(data)+4)//5
        if total == 0:
            source.reply(rtr("command.list.nodata"))
            return
        if page < 1 or page > total:
            source.reply(rtr("command.list.page_outofindex"))
            return
        for i in data[(page-1)*5:min(len(data), page*5)]:
            source.reply(Display.show(i["waypoint"], i["id"]))
        pre = rtr("command.list.pre").h(rtr(f"command.list.{'end' if page == 1 else 'pre'}_prompt"))
        if page != 1:
            pre = pre.c(RAction.run_command, f"{self.prefix} list {page-1}")
        next = rtr("command.list.next").h(rtr(f"command.list.{'end' if page == total else 'next'}_prompt"))
        if page != total:
            next = next.c(RAction.run_command, f"{self.prefix} list {page+1}")
        source.reply(RTextList(rtr("command.list.left"), pre, rtr("command.list.page", current=page, total=total), next, rtr("command.list.right")))
    

    def search(self, source: CommandSource, context: CommandContext):
        name = context["name"]
        target = self.waypoint_manager.search_name(name)
        if not target:
            source.reply(rtr("command.search.nodata", name=name))
            return
        source.reply(rtr("command.search.title", name=name, count=len(target)))
        for i in target:
            source.reply(Display.show(i["waypoint"], i["id"]))
    

    def info(self, source: CommandSource, context: CommandContext):
        id = context["id"]
        waypoint = self.waypoint_manager.search_id(id)
        if not waypoint:
            source.reply(rtr("command.info.nodata"))
        source.reply(rtr("command.info.show", id=waypoint["id"], creator=waypoint["creator"], create_time=waypoint["create_time"], **waypoint["waypoint"].to_dict()))
    

    @new_thread(f"{PLUGIN_ID}-player_pos")
    def player_pos(self, source: CommandSource, context: CommandContext, player: str):
        player_list = self.api.get_player_list()
        server = source.get_server()
        if player not in player_list:
            server.say(rtr("command.player_pos.nodata"))
        player_pos = self.api.get_player_pos(player)
        if not player_pos:
            return
        waypoint = Waypoint(player_pos["pos"], player_pos["dimension"], player)
        
        server.say(Display.show(waypoint))
        source.get_server().execute(self.config.player_api.highlight_command.format(player=player))
        closest = self.waypoint_manager.search_closest(player_pos["pos"], player_pos["dimension"], 128)
        if closest:
            server.say(RTextList(rtr("command.player_pos.closest", distance="%.1f"%closest[1]), Display.show(closest[0]["waypoint"], closest[0]["id"])))


    @new_thread(f"{PLUGIN_ID}-on_user_info")
    def on_user_info(self, server: PluginServerInterface, info: Info):
        waypoint = Waypoint.transform_xaero_waypoint(info.content)
        if waypoint:
            search = self.waypoint_manager.search_distance(waypoint.pos, waypoint.dimension, 0)
            if not search:
                server.say(Display.temporary(waypoint, self.config.command.waypoints))
                return
            search = search[0]
            server.say(Display.show(search["waypoint"], search["id"]))
            return
            
        fastsearch = re.match(self.config.command.fastsearch_regex, info.content)
        if not fastsearch:
            return
        name = fastsearch.group("name")
        target = self.waypoint_manager.search_name(name)
        if target:
            server.say(rtr("command.search.title", name=name, count=len(target)))
            for i in target:
                server.say(Display.show(i["waypoint"], i["id"]))
            return
        player_list = self.api.get_player_list()
        if not player_list or name not in player_list:
            server.say(rtr("command.fastsearch.nodata", name=name))
            return
        player_pos = self.api.get_player_pos(name)
        if not player_pos:
            server.say(rtr("command.fastsearch.nodata", name=name))
            return
        waypoint = Waypoint(player_pos["pos"], player_pos["dimension"], name)
        server.say(Display.show(waypoint))
        server.execute(self.config.player_api.highlight_command.format(player=name))
        closest = self.waypoint_manager.search_closest(player_pos["pos"], player_pos["dimension"], 64)
        if closest:
            server.say(RTextList(rtr("command.player_pos.closest", distance="%.1f"%closest[1]), Display.show(closest[0]["waypoint"])))



def on_load(server: PluginCommandSource, prev_module):
    global proxy
    proxy = Proxy(server)

def on_user_info(server: PluginServerInterface, info: Info):
    proxy.on_user_info(server, info)

def on_info(server: PluginServerInterface, info: Info):
    proxy.api.on_info(server, info)