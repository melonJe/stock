import mysql.connector
from mysql.connector import Error


class DBHelper:
    __instance = None

    @staticmethod
    def get_instance():
        """ Static access method. """
        if DBHelper.__instance == None:
            DBHelper()
        return DBHelper.__instance

    def __init__(self):
        """ Virtually private constructor. """
        if DBHelper.__instance != None:
            raise Exception("This class is a singleton!")
        else:
            DBHelper.__instance = self
            try:
                self.connection = mysql.connector.connect(
                    host='localhost',
                    database='mydatabase',
                    user='myuser',
                    password='mypassword'
                )
                if self.connection.is_connected():
                    db_Info = self.connection.get_server_info()
                    print("Connected to MySQL Server version ", db_Info)
                    cursor = self.connection.cursor()
                    cursor.execute("select database();")
                    record = cursor.fetchone()
                    print("You're connected to database: ", record)
            except Error as e:
                print("Error while connecting to MySQL", e)

    def execute_query(self, query):
        """ Execute a SQL query and return the results. """
        cursor = self.connection.cursor()
        cursor.execute(query)
        return cursor.fetchall()

    def __del__(self):
        """ Close the database connection when the object is destroyed. """
        self.connection.close()
        print("Database connection closed.")
