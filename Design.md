**按钮设计**
import { LiquidButton } from "@/components/ui/liquid-glass-button";

export default function DemoOne() {
  return (
    <> 
      <div className="relative h-[200px] w-[800px]"> 
        <LiquidButton className="absolute top-1/2 left-1/2 z-10 -translate-x-1/2 -translate-y-1/2">
          Liquid Glass
        </LiquidButton> 
      </div>
    </>
  )
}


**登录界面设计**
<!DOCTYPE html>

<html lang="zh-CN">

<head>

    <meta charset="UTF-8">

    <meta http-equiv="X-UA-Compatible" content="IE=edge">

    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <title>登录</title>

    <style>

        *{

    margin: 0;

    padding: 0;

    box-sizing: border-box;

    font-family: 'Poppins',sans-serif;

}

body{

    overflow: hidden;

}

section{

    display: flex;

    justify-content: center;

    align-items: center;

    min-height: 100vh;

    background: linear-gradient(to bottom,#f1f4f9,#dff1ff);

}

section .color{

    position: absolute;

    filter: blur(150px);

}

section .color:nth-child(1){

    top: -350px;

    width: 600px;

    height: 600px;

    background: #ff359b;

}

section .color:nth-child(2){

    bottom: -150px;

    left: 100px;

    width: 500px;

    height: 500px;

    background: #fffd87;

}

section .color:nth-child(3){

    bottom: 50px;

    right: 100px;

    width: 500px;

    height: 500px;

    background: #00d2ff;

}

.box{

    position: relative;

}

.box .square{

    position: absolute;

    backdrop-filter: blur(5px);

    box-shadow: 0 25px 45px rgb(0,0,0,0.1);

    border: 1px solid rgb(255,255,255,0.5);

    border-right: 1px solid rgb(255,255,255,0.2);

    border-bottom: 1px solid rgb(255,255,255,0.2);

    background:rgb(255,255,255,0.1);

    border-radius: 10px;

    animation: animate 10s linear infinite;

    animation-delay: calc(-1s*var(--i));

}

/* 动画 */

@keyframes animate{

    0%,100%{

        transform: translateY(-40px);

    }

    50%{

        transform: translate(40px);

    }

}

.box .square:nth-child(1){

    top: -50px;

    right: -60px;

    width: 100px;

    height: 100px;

}

.box .square:nth-child(2){

    top: 150px;

    left: -100px;

    width: 120px;

    height: 120px;

    z-index: 2;

}

.box .square:nth-child(3){

    bottom: 50px;

    right: -60px;

    width: 80px;

    height: 80px;

    z-index: 2;

}

.box .square:nth-child(4){

    bottom: -80px;

    left: 100px;

    width: 50px;

    height: 50px;

}

.box .square:nth-child(5){

    top: -90px;

    left: 140px;

    width: 60px;

    height: 60px;

}

.container{

    position: relative;

    width:400px;

    min-height: 400px;

    background:rgb(255,255,255,0.1);

    border-radius: 10px;

    display: flex;

    justify-content: center;

    align-items: center;

    backdrop-filter: blur(5px);

    box-shadow: 0 25px 45px rgb(0,0,0,0.1);

    border: 1px solid rgb(255,255,255,0.5);

    border-right: 1px solid rgb(255,255,255,0.2);

    border-bottom: 1px solid rgb(255,255,255,0.2);

}

.form{

    position: relative;

    height: 100%;

    width: 100%;

    padding: 40px;

}

.form h2{

    position: relative;

    color: #fff;

    font-size: 24px;

    font-weight: 600;

    letter-spacing: 1px;

    margin-bottom: 40px;

}

.form h2::before{

    content: '';

    position: absolute;

    left: 0;

    bottom: -10px;

    width: 80px;

    height: 4px;

    background: #fff;

}

.form .inputBox{

    width: 100%;

    margin-top: 20px;

}

.form .inputBox input{

    width: 100%;

    background: rgb(255,255,255,0.2);

    border: none;

    outline: none;

    padding: 10px 20px;

    border-radius: 35px;

    border: 1px solid rgb(255,255,255,0.5);

    border-right: 1px solid rgb(255,255,255,0.2);

    border-bottom: 1px solid rgb(255,255,255,0.2);

    font-size: 16px;

    letter-spacing: 1px;

    color: #fff;

    box-shadow: 0 5px 15px rgb(0,0,0,0.05);

}

.form .inputBox input::placeholder{

    color: #fff;

}

.form .inputBox input[type="submit"]{

    background: #fff;

    color: #666;

    max-width: 100px;

    cursor: pointer;

    margin-bottom: 20px;

    font-weight: 600;

}

.forget{

    margin-top: 5px;

    color: #fff;

}

.forget a{

    color: #fff;

    font-weight: 600;

}



    </style>

</head>

<body>

    <section>

        <div class="color"></div>

        <div class="color"></div>

        <div class="color"></div>

        <div class="box">

            <div class="square" style="--i:0;"></div>

            <div class="square" style="--i:1;"></div>

            <div class="square" style="--i:2;"></div>

            <div class="square" style="--i:3;"></div>

            <div class="square" style="--i:4;"></div>

            <div class="container">

                <div class="form">

                    <h2>Login Form</h2>

                    <form>

                        <div class="inputBox">

                            <input type="text" placeholder="Username">

                        </div>

                        <div class="inputBox">

                            <input type="password" placeholder="Password">

                        </div>

                        <div class="inputBox">

                            <input type="submit" value="Login">

                        </div>

                        <p class="forget">Forget Password ?<a href="#">Click Here</a></p>

                        <p class="forget">Don't have an account ?<a href="#">Sign up</a></p>

                    </form>

                </div>

            </div>

        </div>

    </section>

</body>

</html>


**输入框**
import { BorderBeam } from "@/components/ui/border-beam";

function AtSignIcon() {
  return (
    <svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path
        d="M10.4 5.59963V8.59962C10.4 9.07701 10.5896 9.53485 10.9272 9.87242C11.2648 10.21 11.7226 10.3996 12.2 10.3996C12.6774 10.3996 13.1352 10.21 13.4728 9.87242C13.8104 9.53485 14 9.07701 14 8.59962V7.99962C13.9999 6.64544 13.5417 5.33111 12.7 4.27035C11.8582 3.20958 10.6823 2.46476 9.36359 2.15701C8.04484 1.84925 6.66076 1.99665 5.43641 2.57525C4.21206 3.15384 3.21944 4.1296 2.61996 5.34386C2.02048 6.55812 1.84939 7.93947 2.13451 9.26329C2.41963 10.5871 3.14419 11.7756 4.19038 12.6354C5.23657 13.4952 6.54286 13.9758 7.89684 13.9991C9.25083 14.0224 10.5729 13.587 11.648 12.7636M10.4 7.99962C10.4 9.32511 9.32549 10.3996 8 10.3996C6.67452 10.3996 5.6 9.32511 5.6 7.99962C5.6 6.67414 6.67452 5.59963 8 5.59963C9.32549 5.59963 10.4 6.67414 10.4 7.99962Z"
        stroke="#808388"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ChevronDownIcon() {
  return (
    <svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16" fill="none" style={{ transform: "rotate(90deg)" }}>
      <path d="M7 11L10 8L7 5" stroke="#8B9099" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" opacity="0.6" />
    </svg>
  );
}

function ArrowUpIcon() {
  return (
    <svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path d="M8 12.6667V3.33333M12.6667 8L8 3.33333L3.33333 8" stroke="#8B8B8B" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

const CHIP: React.CSSProperties = {
  borderRadius: 36,
  background: "rgba(255,255,255,0.04)",
  boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.02), inset 0 1px 0 0 rgba(255,255,255,0.04)",
};

function ChatInput() {
  return (
    <div
      style={{
        width: 348,
        maxWidth: "100%",
        borderRadius: 20,
        background: "#1d1d1d",
        boxShadow: "inset 0 0 0 1px rgba(44,47,54,0.52), inset 0 0 50px 0 rgba(255,255,255,0.02)",
        overflow: "hidden",
        position: "relative",
        fontFamily: "system-ui, -apple-system, sans-serif",
      }}
    >
      <div style={{ padding: "7px 7px 8px", display: "flex", flexDirection: "column", height: 122 }}>
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            width: "fit-content",
            height: 24,
            padding: "0 4px",
            marginLeft: 1,
            ...CHIP,
          }}
        >
          <AtSignIcon />
        </div>
        <div style={{ fontSize: 13, lineHeight: "16px", color: "#4e4e4e", padding: "16px 4px 0" }}>Build anything...</div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: "auto" }}>
          <div style={{ display: "inline-flex", alignItems: "center", gap: 4, height: 24, padding: "0 6px 0 8px", fontSize: 12, lineHeight: "14px", color: "#caccd2", marginLeft: 1, ...CHIP }}>
            Agent
            <ChevronDownIcon />
          </div>
          <div style={{ display: "inline-flex", alignItems: "center", gap: 4, height: 24, padding: "0 6px 0 8px", fontSize: 12, lineHeight: "14px", color: "#caccd2", ...CHIP }}>
            Auto
            <ChevronDownIcon />
          </div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", width: 28, height: 28, marginLeft: "auto", padding: "0 8px", ...CHIP }}>
            <ArrowUpIcon />
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Default() {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        width: 600,
        maxWidth: "100%",
        minHeight: 360,
        margin: "0 auto",
        background: "#0d0d0f",
        borderRadius: 24,
      }}
    >
      <BorderBeam size="md" colorVariant="colorful">
        <ChatInput />
      </BorderBeam>
    </div>
  );
}
