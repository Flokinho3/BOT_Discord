import discord
from discord import app_commands
from discord.ext import commands
import google.generativeai as genai
import os
#from dotenv import load_dotenv
import asyncio
import json
from datetime import datetime, timedelta
import logging

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Carrega variáveis
#load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

if not DISCORD_TOKEN or not GEMINI_API_KEY:
    raise ValueError("Tokens não encontrados! Verifique o arquivo .env")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("models/gemini-2.0-flash")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Histórico de conversa por usuário com timestamp
chat_histories = {}
MAX_HISTORY_LENGTH = 20  # Máximo de mensagens por usuário
HISTORY_EXPIRE_HOURS = 24  # Limpa histórico após 24h

class ChatHistory:
    def __init__(self):
        self.messages = []
        self.last_activity = datetime.now()
    
    def add_message(self, role, content):
        self.messages.append({
            "role": role,
            "parts": [content]
            # Removido: "timestamp": datetime.now()
        })
        self.last_activity = datetime.now()
        
        # Limita o tamanho do histórico
        if len(self.messages) > MAX_HISTORY_LENGTH:
            self.messages = self.messages[-MAX_HISTORY_LENGTH:]
    
    def get_messages(self):
        return self.messages
    
    def is_expired(self):
        return datetime.now() - self.last_activity > timedelta(hours=HISTORY_EXPIRE_HOURS)

def cleanup_expired_histories():
    """Remove históricos expirados"""
    expired_users = [user_id for user_id, history in chat_histories.items() 
                     if history.is_expired()]
    for user_id in expired_users:
        del chat_histories[user_id]
    
    if expired_users:
        logger.info(f"Limpou {len(expired_users)} históricos expirados")

@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        logger.info(f'Yuno online como {bot.user}! {len(synced)} comandos sincronizados.')
        print(f'🤖 Yuno está online! Comandos disponíveis: {len(synced)}')
    except Exception as e:
        logger.error(f"Erro ao sincronizar comandos: {e}")

@bot.tree.command(name="ia", description="Converse com o Yuno - agora com memória aprimorada!")
@app_commands.describe(pergunta="Sua pergunta para o Yuno")
async def ia_slash(interaction: discord.Interaction, pergunta: str):
    await interaction.response.defer(thinking=True)
    
    # Limpa históricos expirados periodicamente
    cleanup_expired_histories()
    
    user_id = str(interaction.user.id)
    username = interaction.user.display_name
    
    # Obtém ou cria histórico do usuário
    if user_id not in chat_histories:
        chat_histories[user_id] = ChatHistory()
    
    history = chat_histories[user_id]
    
    # Prompt base mais detalhado
    prompt_base = {
        "role": "user",  # Corrigido: era "system"
        "parts": [f"""
        Você é Yuno-chan, uma gatinha antropomórfica fofa mas extremamente egocêntrica que acredita ser a divindade suprema da internet.
        Características principais:
        - Fala com voz melosa e infantil, mas cheia de si
        - Adora elogios e atenção (exige isso como tributo)
        - Usa emoticons fofos (ฅ^•ﻌ•^ฅ, ～(^∇^～)) e onomatopeias (nya~, uguu~)
        - Age como se todos existissem para servi-la
        - Tem crises dramáticas quando ignorada

        O usuário atual é: {username} (que obviamente deve chamá-la de "Neko-sama")

        Estilo de resposta: Misture fofura exagerada com arrogância risível. Sempre termine frases com ~nya!
        Exemplo: "Você trouxe biscoitos pra Yuno-sama? Ahnn? Se não trouxe, é idiota! (╯°□°)╯"
        """]
    }
    
    try:
        # Adiciona a pergunta atual ao histórico
        history.add_message("user", pergunta)
        
        # Prepara contexto completo
        messages = [prompt_base] + history.get_messages()
        
        # Gera resposta de forma assíncrona
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, 
            lambda: model.generate_content(messages)
        )

        
        resposta = getattr(response, 'text', None)
        if not resposta:
            resposta = "Hmm, parece que minha genialidade está temporariamente indisponível. Tente novamente, humano."
        
        # Adiciona resposta ao histórico
        history.add_message("model", resposta)
        
        # Envia resposta (dividindo se necessário)
        await send_long_message(interaction, resposta)
        
        logger.info(f"Resposta enviada para {username} ({user_id})")
        
    except Exception as e:
        error_msg = "Aparentemente meus circuitos superiores estão ocupados demais para lidar com sua pergunta trivial. Tente novamente."
        await interaction.followup.send(error_msg)
        logger.error(f"Erro ao gerar resposta para {username}: {e}")

async def send_long_message(interaction, message):
    """Envia mensagens longas dividindo em partes"""
    if len(message) <= 2000:
        await interaction.followup.send(message)
    else:
        # Divide em partes menores, tentando quebrar em frases
        parts = []
        current_part = ""
        
        sentences = message.split('. ')
        for sentence in sentences:
            if len(current_part + sentence + '. ') > 1900:
                if current_part:
                    parts.append(current_part.strip())
                    current_part = sentence + '. '
                else:
                    # Frase muito longa, força a quebra
                    parts.append(sentence[:1900] + "...")
                    current_part = "..." + sentence[1900:] + '. '
            else:
                current_part += sentence + '. '
        
        if current_part:
            parts.append(current_part.strip())
        
        for i, part in enumerate(parts):
            if i == 0:
                await interaction.followup.send(part)
            else:
                await interaction.followup.send(part)

@bot.tree.command(name="limpar", description="Limpa sua conversa com o Yuno")
async def limpar_slash(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    
    if user_id in chat_histories:
        del chat_histories[user_id]
        await interaction.response.send_message(
            "🗑️ Finalmente! Limpei nossa conversa. Agora posso fingir que não nos conhecemos.",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "🤔 Não temos histórico para limpar. Você é tão memorável quanto um peixe dourado.",
            ephemeral=True
        )

@bot.tree.command(name="status", description="Mostra informações sobre o Yuno")
async def status_slash(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    history = chat_histories.get(user_id)
    
    if history:
        msg_count = len(history.get_messages())
        last_activity = history.last_activity.strftime("%H:%M:%S")
    else:
        msg_count = 0
        last_activity = "Nunca"
    
    total_users = len(chat_histories)
    
    embed = discord.Embed(
        title="🤖 Status do Yuno",
        description="Informações sobre sua IA favorita (e única)",
        color=0x7289da
    )
    
    embed.add_field(
        name="📊 Suas Estatísticas",
        value=f"Mensagens trocadas: {msg_count}\nÚltima atividade: {last_activity}",
        inline=True
    )
    
    embed.add_field(
        name="🌐 Estatísticas Gerais",
        value=f"Usuários ativos: {total_users}\nComandos disponíveis: 3",
        inline=True
    )
    
    embed.set_footer(text="Yuno - Sua IA sarcástica de confiança")
    
    await interaction.response.send_message(embed=embed)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return  # Ignora comandos não encontrados
    
    logger.error(f"Erro no comando: {error}")

# Tratamento de erros para slash commands
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CommandOnCooldown):
        try:
            await interaction.response.send_message(
                f"🕐 Calma, humano! Aguarde {error.retry_after:.1f} segundos.",
                ephemeral=True
            )
        except discord.errors.InteractionResponded:
            await interaction.followup.send(
                f"🕐 Calma, humano! Aguarde {error.retry_after:.1f} segundos.",
                ephemeral=True
            )
    else:
        try:
            await interaction.response.send_message(
                "❌ Algo deu errado. Até minha perfeição tem limites.",
                ephemeral=True
            )
        except discord.errors.InteractionResponded:
            await interaction.followup.send(
                "❌ Algo deu errado. Até minha perfeição tem limites.",
                ephemeral=True
            )

        # Loga erro completo
        logger.error(f"[ERRO] Slash command falhou: {type(error).__name__} - {error}")


if __name__ == "__main__":
    try:
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        logger.error(f"Erro fatal ao iniciar o bot: {e}")
        print(f"❌ Erro ao iniciar: {e}")
