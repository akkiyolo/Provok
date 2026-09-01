import asyncio
import getpass
from backend.app.database.core import async_session_factory
from backend.app.models.user import User
from backend.app.auth.security import get_password_hash
from sqlalchemy import select

async def main():
    print("Resetting password for akshatshukla069@gmail.com")
    new_password = getpass.getpass("Enter your desired password: ")
    
    async with async_session_factory() as session:
        user = (await session.scalars(select(User).where(User.email == 'akshatshukla069@gmail.com'))).first()
        if not user:
            print("User not found!")
            return
            
        user.password_hash = get_password_hash(new_password)
        await session.commit()
        print("\nSuccess! Your password has been updated in the database.")
        print("You can now delete this script and log in normally.")

if __name__ == "__main__":
    asyncio.run(main())
