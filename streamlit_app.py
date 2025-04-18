from collections import defaultdict
from pathlib import Path
from time import sleep
import streamlit as st
import altair as alt
import pandas as pd
import base64, json
import requests
from io import StringIO
import numpy as np
import re
import unicodedata
from datetime import datetime

import io
import psycopg2
from psycopg2 import sql
from utils.st_login import check_password



#database is on https://cloud.tembo.io/

CLAN_NAME = "SYD"

# Set the title and favicon that appear in the Browser's tab bar.
st.set_page_config(
    page_title=f"{CLAN_NAME} transfers",
    page_icon=":recycle:",  # This is an emoji shortcode. Could be a URL too.
)



# Clan list 

link_template = "https://www.armyneedyou.com/team/user_export?type=current&dateType=lastday&token=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9."

clan_names = {}

#clan_names[148355] = "NTV1" # ex TW1
clan_names[35618] ="SYD" # ex VNE
clan_names[ 835 ] = "SYD2" # ex NWO
clan_names[111] ="SYD3" # ex VNE
clan_names[ 133909 ] = "SYD4" # ex NWO

#clan_names[151] ="VNE1"
#clan_names[ 47257] = "RES1"
#clan_names[ 10283] = "RES2"
#clan_names[ 115] = "RES3"
#clan_names[ 4023] = "RES5"
#clan_names[ 120420] = "RES6"
#clan_names[ 3037] = "RES7"
#clan_names[ 140409] = "BRA1"
#clan_names[ 8961] = "BRA2"
#clan_names[ 96873] = "BRA3"
#clan_names[ 103475] = "BRA4"
##clan_names[ 111] = "BRA5" # bra5
#clan_names[ 434] = "BRA6"
#clan_names[ 4200] = "BRA7"
#clan_names[ 124511] = "BRA8"
#clan_names[ 5425] = "SH1"
#clan_names[ 143430] = "SH2"
#clan_names[ 133909] = "SH3"
#clan_names[142364] = "ARB"
#clan_names[168017] ="VNE3"

#clan_names[4860] = "TW2"
#clan_names[149734] = "TW3"
#clan_names[121740] = "TW4"
#clan_names[119001] = "TW5"


# lets populate a reverse table to ease lookups
clan_ids = {}
for k, v in clan_names.items():
    family = re.sub(r'\d+', '',v)
    # add new families
    if family not in clan_ids.keys():
        clan_ids[family]= [ k ]
    else :
        clan_ids[family].append(k)




possible_families = list(clan_ids.keys())
possible_families  = possible_families[1:] # all teams but NTV
 
# Function to normalize and replace fancy letters
def replace_fancy_letters(text, remove_numbers=False):
    # Normalize to NFKD form (compatibility decomposition)
    normalized_text = unicodedata.normalize('NFKD', text)
    # Filter out non-ASCII characters
    ascii_text = ''.join([char for char in normalized_text if char.isascii()])

    #remove whitespaces
    ascii_text = re.sub(r'\s+', '', text)
    if remove_numbers:
        #remove numbers
        ascii_text = re.sub(r'\d+', '', ascii_text )

    # Convert to uppercase
    return ascii_text.upper()




# -----------------------------------------------------------------------------
# Declare some useful db functions.

# Function to check if a table exists in the PostgreSQL database
def check_table_exists(cursor, table_name):
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = %s
        );
    """, (table_name,))
    return cursor.fetchone()[0]  # Returns True if the table exists, False otherwise


def connect_db():
    """Connects to the pgsql database."""
    # PostgreSQL connection (remote)
    conn = psycopg2.connect(
        host=st.secrets.DB_HOST,
        port=st.secrets.DB_PORT,
        user=st.secrets.DB_USER,
        password=st.secrets.DB_PASS,  # replace with your actual password
        dbname="postgres"  # the default database
    )
    pg_cursor = conn.cursor()
    db_already_exists = check_table_exists(pg_cursor, 'players') and check_table_exists(pg_cursor, 'generals')
    db_was_just_created = not db_already_exists


    return conn, db_was_just_created


def initialize_data(conn):
    """Initializes the players table with no data."""
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS players (
            player_id INTEGER PRIMARY KEY,
            player_name TEXT,
            clan TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS generals (
            clan_id SERIAL PRIMARY KEY,
            player_id INTEGER REFERENCES players(player_id)
        );
        """
    )
    query = f"""
        INSERT INTO players
            (player_id , player_name,  clan)
        VALUES
            (0,'','')
        ON CONFLICT (player_id) DO NOTHING;
        """
    cursor.execute( query )

    conn.commit()

def add_generals(conn):
    """ migration : Initializes the generals table with some data. """
    
    empty_general_list = ""
    for k, _ in clan_names.items():
        empty_general_list = f""" {empty_general_list}
        ({k},0),"""


    cursor = conn.cursor()
    query = f"""
        INSERT INTO generals
            (clan_id , player_id)
        VALUES
            {empty_general_list.strip(",")}
        ON CONFLICT (clan_id) DO NOTHING;
        """

    cursor.execute( query )
    conn.commit()

def add_new_player(id, name):
    cursor = conn.cursor()
    cursor.execute(
        f"""
        INSERT INTO players
            (player_id , player_name,  clan)
        VALUES
            ({id}, '{name}','')
        ON CONFLICT (player_id) DO NOTHING;
        """
    )
    conn.commit()

def add_new_general(clan_id, player_id):
    cursor = conn.cursor()
    cursor.execute(
        f"""
        INSERT  INTO generals
            (clan_id , player_id)
        VALUES
            ({clan_id}, {player_id})
        ON CONFLICT (clan_id) DO NOTHING;
        """
    )
    conn.commit()

def add_or_update_player(conn, id, name,clan):
    cursor = conn.cursor()
    cursor.execute(
        f"""
        INSERT  INTO players
            (player_id , player_name,  clan)
        VALUES
            ({id}, '{name}',  '{clan}')
        ON CONFLICT (player_id) DO NOTHING;
        """
    )

    cursor.execute(  
        f"""
        UPDATE players 
        SET
            player_name = '{name}', clan = '{clan}'
        WHERE 
            player_id = {id} 
        """
    )
    conn.commit()


def add_or_update_general(clan_id, player_id):
    cursor = conn.cursor()

    query =   f"""
        INSERT INTO generals
            (clan_id , player_id)
        VALUES
            ({clan_id}, {player_id})
        ON CONFLICT (clan_id) DO NOTHING;
        """
    print(query)
    cursor.execute(query    )


    query2 = f"""
        UPDATE generals 
        SET
            player_id = {player_id}
        WHERE 
            clan_id = {clan_id} 
        """
    print(query2)
    cursor.execute(query2    )
    conn.commit()


def load_players_data(_conn):
    """Loads the players data from the database."""
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM players")
        data = cursor.fetchall()
    except:
        return None

    df = pd.DataFrame(
        data,
        columns=[
            "player_id",
            "player_name",
            "clan",
        ],
    )
    return df

def clan_name_for_id (row):
    if 'clan_id' in row and row['clan_id'] in clan_names.keys():
        return clan_names[row['clan_id']]
    return ''

def player_name_for_id (row, playerdf):
    if 'player_id' in row and playerdf[playerdf['player_id'] == row['player_id']]:
        line = playerdf[playerdf['player_id'] == row['player_id']]
        return line["Name"].values[0]          
    return ''

def load_generals_data(_conn):
    """Loads the generals data from the database."""
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM generals")
        data = cursor.fetchall()
    except Exception as e:
        print(e)
        return None

    df = pd.DataFrame(
        data,
        columns=[
            "clan_id",
            "player_id"
        ],
    )
    df['clan_name'] =  df.apply(clan_name_for_id ,axis =1)

    #drop rows that do not correspond to a listed clan (no name)
    df = df[df['clan_name'] != '']
    return df

def batch_update_players(_conn, df,  player_df):
    """Check whether reports players are in the dB and add them and if db clan is up to date or update it."""
    


    # Convert 'p_id' columns in both df1 and df2 to string type
    df['player_id'] = df['player_id'].astype(int)
    player_df['player_id'] = player_df['player_id'].astype(int)
    df['player_name'] = df['player_name'].astype(str)
    player_df['player_name'] = player_df['player_name'].astype(str)
    df['clan'] = df['clan'].astype(str)
    player_df['clan'] = player_df['clan'].astype(str)

    new_rows = df[~df['player_id'].isin(player_df['player_id'])]


    if len(new_rows)  > 0 :
        st.write("new_players")
        st.dataframe(new_rows)

        # Result: updated_df2 only contains rows that are new or updated
        data_to_update = new_rows.to_dict(orient='records')
        

        cursor = conn.cursor()
        cursor.executemany(
                """
                INSERT INTO players (player_id, player_name, clan)
                VALUES (%(player_id)s, %(player_name)s, %(clan)s)
                ON CONFLICT (player_id) DO NOTHING;
                """,
                data_to_update,
            )
        
    # Find rows where player_id exists in both but with different values
    common_rows = df[df['player_id'].isin(player_df['player_id'])]

    # Merge to compare columns (excluding player_id from comparison)
    merged = common_rows.merge(player_df, on='player_id', how='left', suffixes=('_df2', '_df1'))


    # Find rows where values differ (compare each column in df2 to df1)
    merged["is_equal"] = (merged["clan_df2"]  == merged["clan_df1"]) & ( merged["player_name_df2"]  == merged["player_name_df1"])
    updated_rows = merged[ merged["is_equal"] == False        ]

    updated_rows = updated_rows[[col for col in merged.columns if not '_df1' in col]].copy()
    updated_rows.columns = updated_rows.columns.str.replace('_df2', '')


    if len(updated_rows)  > 0 :

        st.write("updated players")
        st.dataframe(updated_rows)

        # Result: updated_df2 only contains rows that are new or updated
        data_to_update = updated_rows.to_dict(orient='records')
        

        cursor = conn.cursor()
        cursor.executemany(
                """
                UPDATE players
                SET
                    player_name = %(player_name)s,
                    clan = %(clan)s
                WHERE player_id = %(player_id)s
                """,
                data_to_update,
            )
    
    conn.commit()

def update_players_data(conn, df, changes):
    """Updates the players data in the database after the clan is manually edit in UI."""
    cursor = conn.cursor()
    print(f"""saving {len(changes["edited_rows"])} changes""")
    if changes["edited_rows"]:
        deltas = st.session_state.player_table["edited_rows"]
        rows = []

        for i, delta in deltas.items():
            row_dict = df.iloc[i].to_dict()
            row_dict.update(delta)
            #make it latin letters uppercase
            row_dict["clan"] = replace_fancy_letters(row_dict["clan"], remove_numbers=True)

            if row_dict["clan"]  is None or row_dict["clan"] in possible_families :
                rows.append(row_dict)
                print( f"updating {str(row_dict)}")
            else :
                st.toast(f"Invalid clan of origin `{row_dict['clan']}` for player {row_dict['player_name']}. Value must be in {str(possible_families)}")

        print(str(rows))    
        cursor.executemany(
            """
            UPDATE players
            SET
                player_name = %(player_name)s,
                clan = %(clan)s
            WHERE player_id = %(player_id)s
            """,
            rows,
        )

    if changes["added_rows"]:
        print(f"""New players {str(changes["added_rows"])} """)
        cursor.executemany(
            """
            INSERT INTO players
               ( player_id, player_name , clan)
            VALUES
                ( %(player_id)s , %(player_name)s, %(clan)s)
            ON CONFLICT (player_id) DO NOTHING;
            """,
            (defaultdict(lambda: None, row) for row in changes["added_rows"]),
        )

    if changes["deleted_rows"]:

        print(f"""Deleted players {str(changes["deleted_rows"])} """)
        cursor.executemany(
            "DELETE FROM players WHERE player_id = %(player_id)s",
            ({"player_id": int(df.loc[i, "player_id"])} for i in changes["deleted_rows"]),
        )

    conn.commit()

# Connect to database and create table if needed
conn, db_was_just_created = connect_db()
# Initialize data.
if db_was_just_created:
    initialize_data(conn)
    st.toast("Database initialized with some sample data.")
#add_generals(conn)


# -----------------------------------------------------------------------------
# Draw the actual page, starting with the players table.

# Set the title that appears at the top of the page.
f"""
# :recycle: {CLAN_NAME} transfers

**Welcome to {CLAN_NAME}  transfers site**

*This page prepares {CLAN_NAME}  clan movements.*

"""
if not check_password():
    st.stop()

# Load data from database
players_df = load_players_data(conn)

if not st.session_state["can_write"]: 
    st.warning(f"You have read only access, your changes won't be saved to db")

with st.expander("How to use?"):
    st.markdown(f"""


1. *[Optional]* In the first table, set a clan of origin for {CLAN_NAME}  players that are not identifed as BRA / SH / RES. Those without orgin clan will be first
2. No need to set generals anymore
3. Press the load button to download and process last reset's reports. They are available 2-3 hours after reset

    You get two tables, one with the full player list sorted by rank. A second with all moves
    You may edit the destination clan in the second table, please check that you do not overfill a clan above 50
    You may also download any of the tables as csv to do whatever you want with it in excel

4.  The full transfer list in the format requested by the devs is then available for download in excel format.
""")

st.subheader("Clans of Origin")
st.info(
    f"""
    Use the following table to set a team (RES, BRA, SH, ...) of origin for all {CLAN_NAME}  players.
    When the player no longer qualifies for {CLAN_NAME} , he will be sent to his clan of origin.
    If no clan of origin is set, one will be granted randomly.
    """
)




players_df = players_df.sort_values(by='clan', ascending=True)

players_df['player_id'] = players_df['player_id'].astype(int)
players_df['clan'] = players_df['clan'].astype(str)
players_df['player_name'] = players_df['player_name'].astype(str)

#generals_df = load_generals_data(conn)

#generals_df['clan_id'] = generals_df['clan_id'].astype(int)
#generals_df['player_id'] = generals_df['player_id'].astype(int)

col1,col2 = st.columns([3,2])

with col1:
# Display data with editable table
    edited_df = st.data_editor(
        players_df,
        num_rows="dynamic",  # Allow appending/deleting rows.
        column_config={
            # Show dollar sign before price columns.
            #"price": st.column_config.NumberColumn(format="$%.2f"),
            #"cost_price": st.column_config.NumberColumn(format="$%.2f"),
        },
        key="player_table",
    )
    has_uncommitted_changes = any(len(v) for v in st.session_state.player_table.values())

with col2:
    st.button(
        ":warning: Save Changes",
        type="primary",
        disabled=not has_uncommitted_changes or st.session_state["can_write"] == False,
        # Update data in database
        on_click=update_players_data,
        args=(conn, players_df, st.session_state.player_table),
    )

#st.subheader("Generals")

#st.info("It is mandatory to have un up to date list of generals")

#col1,col2 = st.columns([3,2])
#generals_df['priority'] = generals_df['clan_name'].apply(lambda x: f"0{x}" if x.startswith('NW') else f"1{x}" )

#generals_df =  generals_df.sort_values(by='priority')
#generals_df.drop(columns=['priority'])
#generals_df.reset_index(inplace=True)

#generals_df['player_name']= generals_df['player_id'].apply( lambda player_id :  '' if player_id == 0 else players_df[ players_df['player_id'] == player_id]['player_name'].values[0] )

# Display data withnot editable
#with col1: 
#    st.dataframe(
#        generals_df,
#        column_order = ("clan_id", "clan_name",   "player_id",  "player_name"),   
#    )
#               
#with col2: 
#    with st.container(border=True):
#        st.write("Change a General")
#        generals_have_uncommitted_changes = False
#        last_gen_clan = None
#        last_gen_name = None
#
#        new_general_clan = st.selectbox("Clan",options = clan_names.values(), index = None)
#        new_general_name = st.selectbox("General",options =players_df['player_name'], index = None)
#
#       edited = new_general_clan is not None  and new_general_name is not None
#
#        if st.button(":warning: Save Changes",  
#                     disabled = not edited or st.session_state["can_write"] == False
#            , key="generalbutt"):
#            new_general_id = players_df[ players_df['player_name'] == new_general_name ]['player_id'].values[0]
#            new_general_clan_id = None
#            for k,v in clan_names.items():
#                if v == new_general_clan :
#                    new_general_clan_id = k
#                    break
#            last_gen_clan = new_general_clan
#            last_gen_name = new_general_name      
#            add_or_update_general(clan_id=new_general_clan_id, player_id=new_general_id)
#
#            st.rerun()
        

                    




st.subheader("Pull last reset reports from aow")
st.info(
    """
    Use the following button to pull last available reset ranks from AOW and edit movements
    """
)

    
def assign_users(df,tag):
    print(df.head())
    df2 = df[['ID','Name' ,'Team']]
    df2  =  df2.rename(columns={'ID': 'player_id', 'Name': 'player_name','Team':'clan'})
    batch_update_players(conn, df2, players_df)

   

def create_new_users(df):
    for _, row in df.iterrows():
        id = row['ID']
        name = row['Name']
        add_new_player(id,name)


# Function to fill missing values with a random choice from possible_values
def fill_missing_values(row):

    matching_row = players_df[players_df['player_id'] - row['ID'] == 0]
    clan = matching_row['clan'].values[0] if not matching_row.empty else None
    if clan and len(clan) > 0:
        return clan
    else :
        print(f"not found {row['ID']}  {row['Current Clan Name']} ")
        #print(matching_row)
    return np.random.choice(possible_families)
    

if st.button(f"Reload players ranks from {CLAN_NAME} "):
    from utils.aow_links import pull_all_aow_links
    with st.spinner(f"Pulling {CLAN_NAME} reports"): 
        df_nwo= pull_all_aow_links(CLAN_NAME, clan_ids,clan_names)
        st.session_state.players_ranks_df = df_nwo
        new_df_nwo =  df_nwo[~df_nwo['ID'].isin(players_df['player_id'])]
        create_new_users(new_df_nwo)
        st.session_state.players_ranks_df = df_nwo

    for key in clan_ids.keys():
        if key != CLAN_NAME:
            with st.spinner(f"Pulling {key} report"): 
                sleep(1)
                df_team = pull_all_aow_links(key, clan_ids,clan_names)
                #if key == "TW":
                create_new_users(df_team)
                #else :
                #    assign_users(df_team,key)
                st.session_state.players_ranks_df = pd.concat([st.session_state.players_ranks_df,df_team ])

    

   

    st.session_state.players_ranks_df = st.session_state.players_ranks_df.sort_values(by='Trophies', ascending=False)
    print("before apply len",len(st.session_state.players_ranks_df))
    st.session_state.players_ranks_df['ID'] =  pd.to_numeric(st.session_state.players_ranks_df['ID'], errors='coerce')

    st.session_state.players_ranks_df['origin'] = st.session_state.players_ranks_df.apply(fill_missing_values, axis=1)
    print("after apply len",len(st.session_state.players_ranks_df))

    st.rerun()

if "players_ranks_df" in st.session_state:
    st.subheader("Full player list")
    ## All players
    st.dataframe(st.session_state.players_ranks_df )

    
    st.session_state.moves = ""
    ## Moves to {CLAN_NAME} 
    print(clan_ids[CLAN_NAME])

    nwo_clan_count = len( clan_ids[CLAN_NAME])
    st.session_state.movesdf = pd.DataFrame(columns=[
            "player_id",
            "from",
            "destination",
            "player_name",
            "origin",
            "current team",
            "dest team", 
            "trophies"]
            )
    
    # we will sort 50 player per team, on a list with the generals
   

    # to prevent that, we need to sort 49 player per clan and ignore one player, preferably in the middle of the clan

   


    st.session_state.players_ranks_df['player_id'] = st.session_state.players_ranks_df['ID']
    merged_df = st.session_state.players_ranks_df
#    merged_df = generals_df.merge(st.session_state.players_ranks_df[['player_id', 'Name', 'Current Clan']], 
#                             on= 'player_id', 
#                             how='left', 
#                             )
    
    # Create 'at_home' column where clan_id in general_df matches clan_id in player_df
    merged_df['at_home'] = merged_df['clan_id'] == merged_df['Current Clan']
    # Replace NaN values in the 'Name' column with an empty string
    merged_df['Name'] = merged_df['Name'].fillna('?')
    merged_df['name_clan'] = merged_df['Name'] + ' (' + merged_df['clan_name'] + ')'
#    wandering_generals = merged_df[  merged_df['at_home']  == False ]
#    if not wandering_generals['name_clan'].empty:
#        st.warning(f"The following listed Generals are not even in their clan {str(wandering_generals['name_clan'].tolist())}")
#    def find_middle_player(clan_id):
#        # Filter player_df by clan_id
#        clan_players = st.session_state.players_ranks_df[st.session_state.players_ranks_df['Current Clan'] == clan_id]
#        
#        if not clan_players.empty:
#            # Get the middle index
#            middle_index = len(clan_players) // 2
#            # Select the player at the middle index
##            middle_player = clan_players.iloc[middle_index]
#            return middle_player['player_id']
#        else:
#            return None  # No players in this clan
        
#    def replace_general(general_row):
#        if general_row['at_home']:
#            return general_row['player_id']  # Keep original general if at home
#        else:
#            return find_middle_player(general_row['clan_id'])  # Replace if not at home
        

    # Apply the function to find replacements for non-home generals
#    merged_df['new_general'] = merged_df.apply(replace_general, axis=1)
#    st.session_state.players_ranks_df['cant_move'] = st.session_state.players_ranks_df['ID'].apply( lambda player_id :  player_id in merged_df['new_general'].tolist() )

    players_excepted_generals_df = st.session_state.players_ranks_df #[st.session_state.players_ranks_df['cant_move']  == False]
    for index, nwo_clan_id in enumerate(clan_ids[CLAN_NAME]):
        for _, row in players_excepted_generals_df.iloc[50*index:50+50*index].iterrows():
            #if row["Current Clan"] != nwo_clan_id:
            #st.session_state.movesdf =  f"{st.session_state.moves}\n{row["ID"]} - {row["Current Clan"]} - {nwo_clan_id}"
            
            # New row to add
            new_row = {"player_id" : row["ID"],
                "from": row["Current Clan"],
                "destination": nwo_clan_id,
                "player_name": row["Name"],
                "current team":row["Current Clan Name"],
                "origin":row["origin"],
                "dest team" : clan_names[nwo_clan_id] if nwo_clan_id in  clan_names else nwo_clan_id,
                "trophies" : row["Trophies"]
            }
            # Add the new row using loc
            st.session_state.movesdf.loc[len(st.session_state.movesdf )] = new_row

    remaining_players_df = players_excepted_generals_df.iloc[50*nwo_clan_count:]

    clans_to_sort = possible_families
    for clan_to_sort in clans_to_sort: 
    
        remaining_players_clan = remaining_players_df[remaining_players_df['origin'] == clan_to_sort]
        for index, target_clan_id in enumerate(clan_ids[clan_to_sort]):
            for _, row in remaining_players_clan[50*index:50+50*index].iterrows():
                #if row["Current Clan"] != target_clan_id:
                # New row to add
                new_row = {"player_id" : row["ID"],
                    "from": row["Current Clan"],
                    "destination": target_clan_id,
                    "player_name": row["Name"],
                    "current team":clan_names[row["Current Clan"]] if row["Current Clan"] in  clan_names else "",
                    "origin":row["origin"],
                    "dest team" : clan_names[target_clan_id] if target_clan_id in  clan_names else clan_to_sort,
                    "trophies" : row["Trophies"]
                    }
                # Add the new row using loc
                st.session_state.movesdf.loc[len(st.session_state.movesdf )] = new_row

def check_dest_team(row):
    new_dest_team = replace_fancy_letters(row["dest team"])
    key = None
    for k, v in clan_names.items():
        if v == new_dest_team:
            key = k
            break 
    if key is None :
        st.toast(f"Unknown team {new_dest_team}", icon="🚨")
    #print(key, row["dest team"])
    return key



if "movesdf" in st.session_state.keys() :
    ## Moves
    st.subheader("Moves")
    st.info("""
    Use this table to check moves and edit dest team.
    The table below will be recalculated after each edit, 
    make sure that clans are full but not over 50. 
            
    """)
    filter_moves_only = st.checkbox("Filter on moves only")
   
    filtered_moves_df= st.session_state.movesdf[ st.session_state.movesdf['from'] !=  st.session_state.movesdf['destination'] ]  if filter_moves_only else st.session_state.movesdf
    edited_movesdf = st.data_editor(
        filtered_moves_df,
        num_rows="dynamic",
        disabled=("player_id",
            "from",
            "destination",
            "player_name",
            "origin",
            "current team","tophies"),
        column_order = ("player_id",
            "from",
            "destination",
            "player_name",
            "origin", 
            "current team","dest team" ,"trophies")
        ) 
    if edited_movesdf is not None  and not edited_movesdf.equals(st.session_state.movesdf):
        edited_movesdf['destination']=edited_movesdf.apply(check_dest_team,axis=1)
        edited_movesdf['dest team']=edited_movesdf['dest team']
        st.session_state.movesdf = edited_movesdf
    
    st.subheader("Players per team")
    st.info("""
    Count of players in each of our teams if we do the transfers        
    """)

    col1,col2,col3,col4= st.columns([1,1,1,1])
    cols = [col1, col2, col3, col4]
    index = 0 
    for key in clan_ids.keys():
        with cols[index % len(cols)]:
            index += 1
            ldf = edited_movesdf[edited_movesdf['dest team'].str.contains(key, case=False, na=False)]["dest team"].value_counts() +1 
            st.dataframe(ldf)
    

    export_df = st.session_state.movesdf[ st.session_state.movesdf['from'] !=  st.session_state.movesdf['destination'] ] 
    export_df = export_df.sort_values(by=['from', 'destination'])   
    export_df = export_df.rename(columns={'from': 'from_clan_id', 'destination': 'to_clan_id', 'origin':'family'})
    # Get the current date in YYYY-MM-DD format
    current_date = datetime.now().strftime("%Y-%m-%d")
    file_name = f"{CLAN_NAME}_Rotations_{current_date}"

    # Function to convert DataFrame to Excel and return as a downloadable object
    def to_excel(df):
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        processed_data = output.getvalue()
        return processed_data

    # Create an Excel file for download
    excel_data = to_excel(export_df)
    # Create a button for downloading the Excel file
    col1, col2 , _ , _= st.columns([1,1,1,1])
    with col1: 
        st.download_button(
            label="Download Excel file",
            data=excel_data,
            file_name=f"{file_name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    count = len(export_df)

    st.write(f"{count} Movements / {len(st.session_state.players_ranks_df)} Ranked players")

  
