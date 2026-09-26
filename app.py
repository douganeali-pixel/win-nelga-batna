from flask import Flask, render_template, request, redirect, url_for, session
import psycopg2
from psycopg2.extras import DictCursor
import os
import uuid

app = Flask(__name__)

@app.route("/robots.txt")
def robots():
    return app.send_static_file("robots.txt")


@app.errorhandler(404)
def page_not_found(error):
    return render_template("404.html"), 404


@app.route("/manifest.json")
def manifest():
    return app.send_static_file("manifest.json")


@app.route("/sw.js")
def service_worker():
    return app.send_static_file("sw.js")


# =========================
# إعدادات التطبيق
# =========================

app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "change-me-before-production")

DATABASE_URL = os.environ.get("DATABASE_URL")

UPLOAD_FOLDER = "static/uploads"

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# =========================
# قاعدة البيانات
# =========================

class DBCursor:
    def __init__(self, cursor, lastrowid=None):
        self._cursor = cursor
        self._lastrowid = lastrowid

    @property
    def lastrowid(self):
        return self._lastrowid

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


class DBConnection:
    def __init__(self):
        if not DATABASE_URL:
            raise RuntimeError(
                "DATABASE_URL غير موجود في Environment Variables"
            )

        self.conn = psycopg2.connect(
            DATABASE_URL,
            cursor_factory=DictCursor
        )

    def execute(self, query, params=None):
        query = query.replace("?", "%s")

        is_places_insert = (
            query.strip().upper().startswith("INSERT INTO PLACES")
            and "RETURNING ID" not in query.upper()
        )

        if is_places_insert:
            query = query.rstrip().rstrip(";") + " RETURNING id"

        cursor = self.conn.cursor()
        cursor.execute(query, params)

        lastrowid = None

        if is_places_insert:
            row = cursor.fetchone()
            if row:
                lastrowid = row["id"]

        return DBCursor(cursor, lastrowid)

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()


def get_db():
    return DBConnection()


def allowed_file(filename):
    return (
        filename
        and "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )



def is_place_open(place):
    from datetime import datetime

    try:
        now = datetime.now()
        day = str(now.isoweekday())
        days = (place["working_days"] or "1,2,3,4,5,6").split(",")

        if day not in [x.strip() for x in days]:
            return False

        opening = place["opening_time"] or "08:00"
        closing = place["closing_time"] or "18:00"
        current = now.strftime("%H:%M")

        if opening <= closing:
            return opening <= current <= closing

        return current >= opening or current <= closing
    except Exception:
        return False


@app.template_filter("open_status")
def open_status(place):
    return "مفتوح الآن" if is_place_open(place) else "مغلق الآن"


app.jinja_env.globals["is_place_open"] = is_place_open


def init_db():

    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS places (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            address TEXT NOT NULL,
            phone TEXT,
            description TEXT,
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION,
            image TEXT,
            opening_time TEXT DEFAULT '08:00',
            closing_time TEXT DEFAULT '18:00',
            working_days TEXT DEFAULT '1,2,3,4,5,6'
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id SERIAL PRIMARY KEY,
            place_id INTEGER NOT NULL,
            name TEXT,
            rating INTEGER NOT NULL,
            comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (place_id)
            REFERENCES places(id)
            ON DELETE CASCADE
        )
    """)

    # في حالة وجود جدول قديم، نضيف الأعمدة الناقصة
    conn.execute("""
        ALTER TABLE places
        ADD COLUMN IF NOT EXISTS opening_time TEXT DEFAULT '08:00'
    """)

    conn.execute("""
        ALTER TABLE places
        ADD COLUMN IF NOT EXISTS closing_time TEXT DEFAULT '18:00'
    """)

    conn.execute("""
        ALTER TABLE places
        ADD COLUMN IF NOT EXISTS working_days TEXT DEFAULT '1,2,3,4,5,6'
    """)

    conn.execute("""
        ALTER TABLE places
        ADD COLUMN IF NOT EXISTS source TEXT
    """)

    conn.execute("""
        ALTER TABLE places
        ADD COLUMN IF NOT EXISTS verified_at TIMESTAMP
    """)

    conn.execute("""
        ALTER TABLE places
        ADD COLUMN IF NOT EXISTS map_code TEXT
    """)

    conn.commit()
    conn.close()



def seed_initial_places():
    """إضافة الدفعة الأولى من مؤسسات باتنة مرة واحدة فقط."""
    places = [
        (
            "SARL TIRSAM",
            "سيارات وقطع غيار",
            "Z.I Kechida, Batna",
            "033 92 14 40",
            "شركة لخدمات السيارات وقطع الغيار.",
            "AlgeriaYP - Sep 2026"
        ),
        (
            "NARAUTO",
            "سيارات وقطع غيار",
            "Lotissement Djerouedhib, Route de Biskra, Batna",
            "033 81 69 69",
            "خدمات وقطع غيار السيارات.",
            "AlgeriaYP - Sep 2026"
        ),
        (
            "BATNA MOTORS",
            "سيارات",
            "Cité Riadh, en face Casnos, Batna",
            "033 92 35 10",
            "خدمات مرتبطة بالسيارات.",
            "AlgeriaYP - Sep 2026"
        ),
        (
            "EURL MAHDI AUTO",
            "سيارات وقطع غيار",
            "19 Bd du 19 Mars, Route de Biskra, Batna",
            "033 86 00 36 / 033 86 02 70",
            "خدمات وقطع غيار السيارات.",
            "AlgeriaYP - Sep 2026"
        ),
        (
            "KIA AUTO FERHAT",
            "سيارات وقطع غيار",
            "Zone Industrielle Kechida, Batna",
            "033 92 14 41",
            "خدمات السيارات وقطع الغيار.",
            "AlgeriaYP - Sep 2026"
        ),
        (
            "SM Turbo",
            "سيارات وقطع غيار",
            "Batna, Algeria",
            "0697 53 46 43",
            "بيع سيارات متعددة العلامات وخدمات تركيب وإصلاح وتشخيص التوربو.",
            "SM Turbo - Sep 2026"
        ),
        (
            "Kherraf Automobile",
            "صيانة السيارات",
            "Avenue de la Gare, Batna",
            "0660 71 55 17",
            "صيانة وإصلاح السيارات، ميكانيك، كهرباء وتشخيص أعطال.",
            "Kherraf Automobile - Aug 2026"
        ),
        (
            "Massinissa Lounge",
            "مطاعم وحلويات",
            "02 Avenue de l'Indépendance, Batna",
            "0550 53 53 53",
            "مطعم وصالة في باتنة.",
            "Vymaps - Sep 2026"
        ),
        (
            "Planet Food",
            "مطاعم وحلويات",
            "Rue de l'Aures, Batna",
            "0550 38 09 01",
            "مطعم في باتنة.",
            "Vymaps - Sep 2026"
        ),
        (
            "SAE-EXACT Centre Batna",
            "خدمات",
            "Batna, Algeria",
            "033 25 38 18 / 0561 52 52 36",
            "مركز خبرة ومراقبة تقنية للسيارات وخدمات الخبرة.",
            "SAE-EXACT - Sep 2026"
        )
    ]

    # إحداثيات المؤسسات الموثقة
    coordinates = {
        "Massinissa Lounge": (35.552770, 6.176680),
    }

    # إحداثيات موثقة للمؤسسات
    coordinates = {
        "SARL TIRSAM": (35.565170, 6.167940),
        "EURL MAHDI AUTO": (35.561515, 6.160970),
        "Massinissa Lounge": (35.552770, 6.176680),
    }

    conn = get_db()

    try:

        # بيانات الخرائط الموثقة
        map_codes = {
            "SM Turbo": "G5H6+5HQ, Batna, Algeria",
        }

        for place_name, map_code in map_codes.items():
            conn.execute("""
                UPDATE places
                SET map_code = ?,
                    verified_at = CURRENT_TIMESTAMP
                WHERE name = ?
            """, (map_code, place_name))


        # تحديث إحداثيات المؤسسات الموجودة
        for place_name, (lat, lng) in coordinates.items():
            conn.execute("""
                UPDATE places
                SET latitude = ?,
                    longitude = ?,
                    verified_at = CURRENT_TIMESTAMP
                WHERE name = ?
            """, (lat, lng, place_name))

        # تحديث الإحداثيات للمؤسسات الموجودة
        for place_name, (lat, lng) in coordinates.items():
            conn.execute("""
                UPDATE places
                SET latitude = ?,
                    longitude = ?,
                    verified_at = CURRENT_TIMESTAMP
                WHERE name = ?
            """, (lat, lng, place_name))

        for name, category, address, phone, description, source in places:
            existing = conn.execute(
                "SELECT id FROM places WHERE name = ? LIMIT 1",
                (name,)
            ).fetchone()

            if existing is None:
                conn.execute("""
                    INSERT INTO places
                    (
                        name,
                        category,
                        address,
                        phone,
                        description,
                        source,
                        verified_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    name,
                    category,
                    address,
                    phone,
                    description,
                    source
                ))

        conn.commit()
    finally:
        conn.close()


# =========================
# الصفحة الرئيسية
# =========================

@app.route("/")
def home():

    conn = get_db()

    places = conn.execute("""
        SELECT
            places.*,
            ROUND(
                COALESCE(AVG(reviews.rating), 0),
                1
            ) AS average_rating,
            COUNT(reviews.id) AS review_count
        FROM places
        LEFT JOIN reviews
            ON places.id = reviews.place_id
        GROUP BY places.id
        ORDER BY places.id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "index.html",
        places=places
    )


# =========================
# إضافة مكان
# =========================

@app.route("/add", methods=["GET", "POST"])
def add_place():

    if request.method == "POST":

        name = request.form.get(
            "name", ""
        ).strip()

        category = request.form.get(
            "category", ""
        ).strip()

        address = request.form.get(
            "address", ""
        ).strip()

        phone = request.form.get(
            "phone", ""
        ).strip()

        description = request.form.get(
            "description", ""
        ).strip()

        latitude = request.form.get(
            "latitude", ""
        ).strip()

        longitude = request.form.get(
            "longitude", ""
        ).strip()

        # تحويل الإحداثيات
        try:
            latitude = float(latitude)
        except:
            latitude = None

        try:
            longitude = float(longitude)
        except:
            longitude = None

        # الصورة
        image_filename = None

        image = request.files.get("image")

        if image and image.filename:

            if allowed_file(image.filename):

                extension = image.filename.rsplit(
                    ".", 1
                )[1].lower()

                image_filename = (
                    str(uuid.uuid4())
                    + "."
                    + extension
                )

                image_path = os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    image_filename
                )

                image.save(image_path)

        # حفظ المكان
        conn = get_db()

        cursor = conn.execute("""
            INSERT INTO places
            (
                name,
                category,
                address,
                phone,
                description,
                latitude,
                longitude,
                image,
                source,
                verified_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            name,
            category,
            address,
            phone,
            description,
            latitude,
            longitude,
            image_filename,
            request.form.get("source", "إضافة يدوية").strip() or "إضافة يدوية"
        ))

        conn.commit()

        place_id = cursor.lastrowid

        conn.close()

        return redirect(
            url_for(
                "place",
                place_id=place_id
            )
        )

    return render_template("add.html")


# =========================
# البحث
# =========================

# =========================
# قريب مني
# =========================

@app.route("/nearby")
def nearby():

    conn = get_db()

    places = conn.execute("""
        SELECT
            places.*,
            ROUND(COALESCE(AVG(reviews.rating), 0), 1) AS average_rating,
            COUNT(reviews.id) AS review_count
        FROM places
        LEFT JOIN reviews
            ON places.id = reviews.place_id
        WHERE places.latitude IS NOT NULL
          AND places.longitude IS NOT NULL
        GROUP BY places.id
        ORDER BY places.id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "nearby.html",
        places=places
    )


@app.route("/search")
def search():

    query = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()

    conn = get_db()

    base_query = """
        SELECT
            places.*,
            ROUND(COALESCE(AVG(reviews.rating), 0), 1) AS average_rating,
            COUNT(reviews.id) AS review_count
        FROM places
        LEFT JOIN reviews
            ON places.id = reviews.place_id
    """

    if category:

        places = conn.execute(
            base_query + """
            WHERE places.category LIKE ?
            GROUP BY places.id
            ORDER BY places.id DESC
            """,
            (f"%{category}%",)
        ).fetchall()

        title = category

    elif query:

        search_value = f"%{query}%"

        places = conn.execute(
            base_query + """
            WHERE
                places.name LIKE ?
                OR places.category LIKE ?
                OR places.address LIKE ?
                OR places.description LIKE ?
                OR places.phone LIKE ?
            GROUP BY places.id
            ORDER BY places.id DESC
            """,
            (
                search_value,
                search_value,
                search_value,
                search_value,
                search_value
            )
        ).fetchall()

        title = query

    else:

        places = conn.execute(
            base_query + """
            GROUP BY places.id
            ORDER BY places.id DESC
            """
        ).fetchall()

        title = "جميع الأماكن"

    conn.close()

    return render_template(
        "results.html",
        places=places,
        query=title
    )


# =========================
# تفاصيل المكان
# =========================

@app.route("/place/<int:place_id>")
def place(place_id):

    conn = get_db()

    # بيانات المكان
    place_data = conn.execute("""
        SELECT *
        FROM places
        WHERE id = ?
    """, (
        place_id,
    )).fetchone()

    if place_data is None:

        conn.close()

        return "المحل غير موجود", 404

    # التقييمات
    reviews = conn.execute("""
        SELECT *
        FROM reviews
        WHERE place_id = ?
        ORDER BY id DESC
    """, (
        place_id,
    )).fetchall()

    # متوسط التقييم
    average_result = conn.execute("""
        SELECT AVG(rating)
        FROM reviews
        WHERE place_id = ?
    """, (
        place_id,
    )).fetchone()

    if (
        average_result
        and average_result[0] is not None
    ):
        average = round(
            average_result[0],
            1
        )
    else:
        average = 0

    conn.close()

    return render_template(
        "place.html",
        place=place_data,
        reviews=reviews,
        average=average
    )


# =========================
# تعديل المكان
# =========================

@app.route(
    "/edit/<int:place_id>",
    methods=["GET", "POST"]
)
def edit_place(place_id):

    if not session.get("admin"):

        return redirect(
            url_for("admin")
        )

    conn = get_db()

    place_data = conn.execute("""
        SELECT *
        FROM places
        WHERE id = ?
    """, (
        place_id,
    )).fetchone()

    if place_data is None:

        conn.close()

        return "المحل غير موجود", 404

    if request.method == "POST":

        name = request.form.get(
            "name", ""
        ).strip()

        category = request.form.get(
            "category", ""
        ).strip()

        address = request.form.get(
            "address", ""
        ).strip()

        phone = request.form.get(
            "phone", ""
        ).strip()

        description = request.form.get(
            "description", ""
        ).strip()

        latitude = request.form.get(
            "latitude", ""
        ).strip()

        longitude = request.form.get(
            "longitude", ""
        ).strip()

        try:
            latitude = float(latitude)
        except:
            latitude = None

        try:
            longitude = float(longitude)
        except:
            longitude = None

        # الصورة الحالية
        image_filename = place_data["image"]

        image = request.files.get("image")

        if image and image.filename:

            if allowed_file(image.filename):

                extension = image.filename.rsplit(
                    ".",
                    1
                )[1].lower()

                new_image_filename = (
                    str(uuid.uuid4())
                    + "."
                    + extension
                )

                new_image_path = os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    new_image_filename
                )

                image.save(
                    new_image_path
                )

                # حذف الصورة القديمة
                if image_filename:

                    old_image_path = os.path.join(
                        app.config["UPLOAD_FOLDER"],
                        image_filename
                    )

                    if os.path.exists(
                        old_image_path
                    ):
                        os.remove(
                            old_image_path
                        )

                image_filename = (
                    new_image_filename
                )

        # تحديث البيانات
        conn.execute("""
            UPDATE places
            SET
                name = ?,
                category = ?,
                address = ?,
                phone = ?,
                description = ?,
                latitude = ?,
                longitude = ?,
                image = ?,
                opening_time = ?,
                closing_time = ?,
                working_days = ?,
                source = ?,
                verified_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            name,
            category,
            address,
            phone,
            description,
            latitude,
            longitude,
            image_filename,
            request.form.get("opening_time", "08:00").strip() or "08:00",
            request.form.get("closing_time", "18:00").strip() or "18:00",
            request.form.get("working_days", "1,2,3,4,5,6").strip() or "1,2,3,4,5,6",
            request.form.get("source", place_data["source"] if "source" in place_data.keys() else "إضافة يدوية").strip() or "إضافة يدوية",
            place_id
        ))

        conn.commit()

        conn.close()

        return redirect(
            url_for(
                "place",
                place_id=place_id
            )
        )

    conn.close()

    return render_template(
        "edit.html",
        place=place_data
    )


# =========================
# حذف المكان
# =========================

@app.route(
    "/delete/<int:place_id>",
    methods=["POST"]
)
def delete_place(place_id):

    if not session.get("admin"):

        return redirect(
            url_for("admin")
        )

    conn = get_db()

    place_data = conn.execute("""
        SELECT *
        FROM places
        WHERE id = ?
    """, (
        place_id,
    )).fetchone()

    if place_data is None:

        conn.close()

        return "المحل غير موجود", 404

    # حذف الصورة
    if place_data["image"]:

        image_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            place_data["image"]
        )

        if os.path.exists(image_path):

            os.remove(image_path)

    # حذف التقييمات
    conn.execute("""
        DELETE FROM reviews
        WHERE place_id = ?
    """, (
        place_id,
    ))

    # حذف المكان
    conn.execute("""
        DELETE FROM places
        WHERE id = ?
    """, (
        place_id,
    ))

    conn.commit()

    conn.close()

    return redirect(
        url_for("home")
    )


# =========================
# الخريطة
# =========================

@app.route("/map")
def all_map():

    conn = get_db()

    places = conn.execute("""
        SELECT
            places.*,
            ROUND(COALESCE(AVG(reviews.rating), 0), 1) AS average_rating,
            COUNT(reviews.id) AS review_count
        FROM places
        LEFT JOIN reviews
            ON places.id = reviews.place_id
        WHERE places.latitude IS NOT NULL
          AND places.longitude IS NOT NULL
        GROUP BY places.id
        ORDER BY places.id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "map.html",
        places=places
    )


@app.route(
    "/admin",
    methods=["GET", "POST"]
)
def admin():

    if request.method == "POST":

        password = request.form.get(
            "password",
            ""
        )

        if password == ADMIN_PASSWORD:

            session["admin"] = True

            return redirect(
                url_for("admin")
            )

        return render_template(
            "admin_login.html",
            error="كلمة المرور غير صحيحة"
        )

    if not session.get("admin"):

        return render_template(
            "admin_login.html"
        )

    conn = get_db()

    places = conn.execute("""
        SELECT
            places.*,
            ROUND(COALESCE(AVG(reviews.rating), 0), 1) AS average_rating,
            COUNT(reviews.id) AS review_count
        FROM places
        LEFT JOIN reviews
            ON places.id = reviews.place_id
        GROUP BY places.id
        ORDER BY places.id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "admin.html",
        places=places
    )


# =========================
# تسجيل الخروج
# =========================

@app.route("/admin/logout")
def admin_logout():
    if not session.get("admin"):
        return redirect(url_for("admin"))

    session.pop(
        "admin",
        None
    )

    return redirect(
        url_for("home")
    )


# =========================
# إضافة تقييم
# =========================

@app.route(
    "/review/<int:place_id>",
    methods=["POST"]
)
def add_review(place_id):

    name = request.form.get(
        "name",
        ""
    ).strip()

    comment = request.form.get(
        "comment",
        ""
    ).strip()

    try:

        rating = int(
            request.form.get(
                "rating",
                0
            )
        )

    except:

        rating = 0

    if rating < 1 or rating > 5:

        return (
            "التقييم يجب أن يكون بين 1 و5",
            400
        )

    conn = get_db()

    # التأكد من وجود المكان
    exists = conn.execute("""
        SELECT id
        FROM places
        WHERE id = ?
    """, (
        place_id,
    )).fetchone()

    if exists is None:

        conn.close()

        return "المحل غير موجود", 404

    # إضافة التقييم
    conn.execute("""
        INSERT INTO reviews
        (
            place_id,
            name,
            rating,
            comment
        )
        VALUES (?, ?, ?, ?)
    """, (
        place_id,
        name,
        rating,
        comment
    ))

    conn.commit()

    conn.close()

    return redirect(
        url_for(
            "place",
            place_id=place_id
        )
    )


# =========================
# تشغيل التطبيق
# =========================

if __name__ == "__main__":

    init_db()

    app.run(
        debug=True
    )

init_db()
seed_initial_places()

if __name__ == "__main__":
    app.run(debug=True)
