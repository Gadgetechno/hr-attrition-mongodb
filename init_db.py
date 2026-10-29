"""init_db.py
Convenience script to run setup_database, ingest_data, and ml_model in sequence.
Useful for Render build/release steps or one-click database setup.
"""
import setup_database
import ingest_data
import ml_model


def main():
    print("--- 1. Setting up database and schemas ---")
    setup_database.main()
    print("--- 2. Ingesting employee dataset ---")
    ingest_data.main()
    print("--- 3. Training initial ML model ---")
    ml_model.main()
    print("--- Database initialization complete! ---")


if __name__ == "__main__":
    main()
