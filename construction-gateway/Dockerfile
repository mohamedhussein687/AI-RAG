FROM maven:3.9.9-eclipse-temurin-21 AS build
WORKDIR /src
COPY pom.xml .
RUN mvn -B -ntp dependency:go-offline
COPY src ./src
RUN mvn -B -ntp package -DskipTests

FROM eclipse-temurin:21.0.5_11-jre-noble
RUN useradd --system --home /app --shell /usr/sbin/nologin gateway
WORKDIR /app
COPY --from=build /src/target/construction-gateway-0.1.0.jar /app/app.jar
USER gateway
EXPOSE 8080
ENTRYPOINT ["java","-jar","/app/app.jar"]
