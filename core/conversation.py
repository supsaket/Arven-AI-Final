from brain.brain import Brain


class Conversation:

    def __init__(self):
        self.brain = Brain()

    def ask(self, user_message):

        result = self.brain.process(user_message)

        print(f"[DEBUG] Category: {result['category']}")
        print(f"[DEBUG] Memory: {result['memory_action']}")

        return result["response"]

    def run(self):

        print("ARVEN is online.")
        print("Type 'exit' to shut down.")
        print()

        while True:

            try:

                user_input = input("Boss: ").strip()

                if not user_input:
                    continue

                if user_input.lower() in [
                    "exit",
                    "quit",
                    "bye"
                ]:
                    print("ARVEN: Goodbye, Boss.")
                    break

                response = self.ask(user_input)

                print(f"ARVEN: {response}")
                print()

            except KeyboardInterrupt:
                print("\nARVEN: Goodbye, Boss.")
                break

            except Exception as error:
                print(f"ARVEN: I encountered an error: {error}")


if __name__ == "__main__":
    Conversation().run()
