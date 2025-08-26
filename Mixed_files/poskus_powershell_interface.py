number = 0

try:
    while True:
        number += 1
        user_input = input("Enter a word: ")
        print(user_input, number)
        
except EOFError:
    print("EOFError occurred. Exiting the loop.")

except KeyboardInterrupt:
    print("KeyboardInterrupt occurred. Exiting the loop.")