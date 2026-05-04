import discord



class Scanner(discord.Client):
    async def on_ready(self):
        print(f'Logged in as {self.user}')

    async def on_message(self, message):
        if message.author == self.user:
            return

        # Process the message content here
        print(f'Message from {message.author}: {message.content}')

client = Scanner()

client.start("YOUR_USER_TOKEN_HERE")